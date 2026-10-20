import tkinter as tk
from tkinter import scrolledtext, messagebox
from connection_options import parse_options, connection_urls, accepts_code
import time
import threading
from PIL import Image, ImageDraw
from pystray import MenuItem as item, Icon as icon
import sys
import re
import socketio
import pyperclip
from winotify import Notification
from datetime import datetime

# Imports for single-instance lock
from win32event import CreateMutex
from win32api import GetLastError
from winerror import ERROR_ALREADY_EXISTS
import os
import sys

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# --- Configuration ---
# Load from the config file
from config.settings import PRIMARY_URL, SECONDARY_URL
URLS = [PRIMARY_URL, SECONDARY_URL]

class SingleInstance:
    def __init__(self, name):
        self.mutex_name = name
        self.mutex = CreateMutex(None, 1, self.mutex_name)
        self.last_error = GetLastError()

    def already_running(self):
        return self.last_error == ERROR_ALREADY_EXISTS

class App:
    def __init__(self, root, key=None):
        self.root = root
        self.key = key
        self.routing_ready = False
        self.urls = connection_urls(URLS, key)
        self.root.title("쇼핑몰 인증번호")
        self.root.iconbitmap(resource_path('app.ico'))
        self.root.geometry("640x360")
        self.root.configure(bg="white")
        self.tray_icon_thread = None
        self.tray_icon = None

        # Theme: White background, black text
        self.log_area = scrolledtext.ScrolledText(root, wrap=tk.WORD, bg="white", fg="black", relief=tk.FLAT)
        self.log_area.pack(expand=True, fill='both', padx=5, pady=5)
        self.log_area.mark_set('input_start', 'end-1c')
        self.log_area.mark_gravity('input_start', tk.LEFT)
        self.log_area.bind('<Return>', self.submit_model)
        self.log_area.bind('<KeyPress>', self.protect_log)
        self.log_area.bind('<<Paste>>', self.paste_model)
        self.log_area.bind('<<Cut>>', self.protect_cut)
        self.log_area.focus_set()

        self.sio = socketio.Client()
        self.setup_sio_events()

        self.stop_event = threading.Event()
        self.worker_thread = threading.Thread(target=self.socket_io_main_loop, daemon=True)
        self.worker_thread.start()

        # Close button (X) will exit the application
        self.root.protocol("WM_DELETE_WINDOW", self.quit_app)
        # Minimize button (_) will hide the window to the system tray
        self.root.bind("<Unmap>", self.handle_minimize)

    def handle_minimize(self, event):
        # This is triggered when the window is unmapped (e.g., minimized).
        # We check if the state is 'iconic' to confirm it was a minimize action.
        if self.root.state() == 'iconic':
            self.hide_window()

    def is_ip_address(self, url):
        # A simple regex to check for an IP address format (v4) in the URL's hostname
        match = re.search(r':\/\/(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', url)
        return match is not None

    def log(self, message):
        if self.stop_event.is_set():
            return
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        full_message = f"[{timestamp}] {message}\n"
        self.root.after(0, lambda: self.append_log(full_message))

    def append_log(self, message):
        self.log_area.mark_gravity('input_start', tk.RIGHT)
        self.log_area.insert('input_start', message)
        self.log_area.mark_gravity('input_start', tk.LEFT)
        self.log_area.see(tk.END)

    def protect_cut(self, event=None):
        if self.log_area.tag_ranges(tk.SEL) and self.log_area.compare('sel.first', '<', 'input_start'):
            return 'break'

    def protect_log(self, event):
        if not event.char and event.keysym not in ('BackSpace', 'Delete'):
            return
        if event.state & 4 and event.keysym.lower() not in ('backspace', 'delete', 'h', 'd', 'k'):
            return
        if self.protect_cut() == 'break':
            self.log_area.tag_remove(tk.SEL, '1.0', tk.END)
        if self.log_area.compare(tk.INSERT, '<', 'input_start'):
            self.log_area.mark_set(tk.INSERT, 'end-1c')
        if event.keysym == 'BackSpace' and self.log_area.compare(tk.INSERT, '<=', 'input_start'):
            return 'break'
        if event.state & 4 and event.keysym in ('BackSpace', 'h'):
            start = self.log_area.index('insert -1c wordstart')
            if self.log_area.compare(start, '<', 'input_start'):
                start = self.log_area.index('input_start')
            self.log_area.delete(start, tk.INSERT)
            return 'break'

    def paste_model(self, event=None):
        try:
            text = self.root.clipboard_get().replace('\r', ' ').replace('\n', ' ')
        except tk.TclError:
            return 'break'
        if self.log_area.tag_ranges(tk.SEL):
            if self.protect_cut() != 'break':
                self.log_area.delete('sel.first', 'sel.last')
            self.log_area.tag_remove(tk.SEL, '1.0', tk.END)
        if self.log_area.compare(tk.INSERT, '<', 'input_start'):
            self.log_area.mark_set(tk.INSERT, 'end-1c')
        self.log_area.insert(tk.INSERT, text)
        return 'break'

    def submit_model(self, event=None):
        model = self.log_area.get('input_start', 'end-1c').strip()
        if model:
            self.log_area.delete('input_start', 'end-1c')
            self.append_log(f'> {model}\n')
            self.send_product_search(model)
        return 'break'

    def setup_sio_events(self):
        @self.sio.event
        def connect():
            connected_url = self.sio.connection_url
            # 2. IP Obfuscation
            if self.is_ip_address(connected_url):
                self.log("Successfully connected to the fallback IP address.")
            else:
                self.log(f"Successfully connected to {connected_url}")
            if self.key is None:
                self.log("Legacy mode: listening for unkeyed authentication codes.")
            else:
                self.log("Connected. A routing_ready confirmation is required to receive codes.")

        @self.sio.on('routing_ready')
        def on_routing_ready(data):
            self.routing_ready = (isinstance(data, dict) and data.get('version') == 1
                                  and data.get('mode') == 'keyed')

        @self.sio.event
        def disconnect(reason=None):
            self.routing_ready = False
            if self.stop_event.is_set():
                return
            self.log("Disconnected from the server. Attempting to reconnect...")

        @self.sio.on('new_code')
        def on_new_code(data):
            if not accepts_code(data, self.key, self.routing_ready):
                self.log("Code ignored: routing is not confirmed. Check the server version.")
                return
            auth_code = data.get('code')
            filter_value = data.get('filter_value')
            if not auth_code:
                return

            self.log(f"Code received. Filter: {filter_value}, Code: {auth_code}")
            pyperclip.copy(auth_code)
            notification_message = f'{auth_code}가 클립보드에 복사되었습니다.'
            
            try:
                toast = Notification(app_id="쇼핑몰 인증번호", title="인증번호 도착", msg=notification_message)
                toast.show()
            except Exception as e:
                self.log(f"Notification failed: {e}")

    def send_product_search(self, model):
        if not model or len(model) > 200 or any(ord(c) < 32 or ord(c) == 127 for c in model):
            messagebox.showerror("모델명 확인", "상품 모델명을 1~200자로 입력하세요.")
            return
        if not self.key or not self.routing_ready or not self.sio.connected:
            self.log("Search unavailable: connect in pairing-key mode first.")
            return

        def send():
            try:
                result = self.sio.call('open_product_search', {'model': model}, timeout=10)
                if isinstance(result, dict) and result.get('status') == 'sent':
                    self.log(f"Search sent to {result['phones']} connected phone(s).")
                else:
                    self.log(result.get('error', 'Search failed.') if isinstance(result, dict) else 'Search failed.')
            except (socketio.exceptions.SocketIOError, ValueError):
                self.log("Search failed: check the server and phone connection.")

        threading.Thread(target=send, daemon=True).start()

    def socket_io_main_loop(self):
        self.log("Client starting...")
        while not self.stop_event.is_set():
            for url in self.urls:
                if self.stop_event.is_set(): break
                try:
                    # 2. IP Obfuscation
                    if self.is_ip_address(url):
                        self.log("Attempting to connect to the fallback IP address...")
                    else:
                        self.log(f"Attempting to connect to {url}...")
                    
                    self.routing_ready = False
                    auth = {'key': self.key} if self.key is not None else None
                    self.sio.connect(url, auth=auth, wait_timeout=10)
                    self.sio.wait() # Blocks until disconnected
                except socketio.exceptions.ConnectionError:
                    self.log("Failed to connect to the current address.")
                    continue
                except Exception:
                    self.log("An unexpected connection error occurred.")
                    time.sleep(10)
                    continue
            if not self.sio.connected and not self.stop_event.is_set():
                self.log("All connection attempts failed. Retrying in 30 seconds...")
                time.sleep(30)
        self.log("Client worker thread has stopped.")

    def start_tray_icon(self):
        if self.tray_icon_thread and self.tray_icon_thread.is_alive():
            return
        
        image = Image.open(resource_path("app.ico"))
        menu = (
            item('Show', self.show_window, default=True),
            item('Exit', self.quit_app)
        )
        self.tray_icon = icon('shopping-mall-auth-icon', image, "쇼핑몰 인증번호", menu)
        
        self.tray_icon_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        self.tray_icon_thread.start()

    def hide_window(self):
        self.root.withdraw()
        self.start_tray_icon()

    def show_window(self):
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.deiconify()
        self.root.focus_force()

    def quit_app(self):
        self.log("Quitting application...")
        self.stop_event.set()
        if self.sio.connected:
            self.sio.disconnect()
        if self.tray_icon and self.tray_icon.visible:
            self.tray_icon.stop()
        self.root.destroy()

if __name__ == "__main__":
    try:
        options = parse_options()
        if not connection_urls(URLS, options.key):
            raise ValueError('연결키 모드에는 HTTPS 서버 주소가 필요합니다. config/settings.py를 확인하세요.')
    except ValueError as exc:
        error_root = tk.Tk()
        error_root.withdraw()
        messagebox.showerror('실행 설정 확인', str(exc))
        error_root.destroy()
        sys.exit(1)

    instance_lock = SingleInstance("Global\SMSClientAppMutex")
    if instance_lock.already_running():
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showwarning("프로그램 실행 중", "현재 프로그램이 실행중입니다.")
        root.destroy()
        sys.exit(1)

    main_root = tk.Tk()
    app = App(main_root, options.key)
    
    # Start with the window visible and focused
    app.show_window()
    main_root.mainloop()
