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
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        full_message = f"[{timestamp}] {message}\n"
        self.root.after(0, lambda: self.log_area.insert(tk.END, full_message))
        self.root.after(0, lambda: self.log_area.see(tk.END)) # Auto-scroll

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
            if self.routing_ready:
                self.log("연결키 전용 수신이 준비되었습니다. 같은 키의 휴대폰 문자만 수신합니다.")

        @self.sio.event
        def disconnect(reason=None):
            self.routing_ready = False
            self.log("Disconnected from the server. Attempting to reconnect...")

        @self.sio.on('new_code')
        def on_new_code(data):
            if not accepts_code(data, self.key, self.routing_ready):
                self.log("수신 분리가 확인되지 않아 코드를 무시했습니다. 서버 업데이트를 확인하세요.")
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
