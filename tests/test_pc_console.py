import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


@unittest.skipUnless(sys.platform == 'win32', 'Windows PC client')
class ConsoleInputTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'client'))
        import pc_client
        self.root = pc_client.tk.Tk()
        self.root.withdraw()
        with patch.object(self.root, 'iconbitmap'), patch.object(pc_client.threading.Thread, 'start'):
            self.app = pc_client.App(self.root, 'test-key')
        self.text = self.app.log_area

    def tearDown(self):
        self.app.quit_app()

    def test_incoming_logs_preserve_input_and_enter_sends_only_model(self):
        self.app.append_log('Connected\n')
        self.text.insert('end-1c', 'DD1391-100')
        self.app.append_log('Code received\n')
        self.assertEqual(self.text.get('input_start', 'end-1c'), 'DD1391-100')
        with patch.object(self.app, 'send_product_search') as send:
            self.assertEqual(self.app.submit_model(), 'break')
            send.assert_called_once_with('DD1391-100')
            self.app.submit_model()
            send.assert_called_once()
        self.assertEqual(self.text.get('1.0', 'end-1c'), 'Connected\nCode received\n> DD1391-100\n')
        self.assertEqual(self.text.get('input_start', 'end-1c'), '')

    def test_backspace_and_cut_cannot_remove_logs(self):
        self.app.append_log('Connected\n')
        self.text.mark_set('insert', 'input_start')
        event = SimpleNamespace(char='\b', keysym='BackSpace', state=0)
        self.assertEqual(self.app.protect_log(event), 'break')
        self.text.tag_add('sel', '1.0', 'end-1c')
        self.assertEqual(self.app.protect_cut(), 'break')
        self.assertEqual(self.text.get('1.0', 'end-1c'), 'Connected\n')

    def test_pasting_over_selected_logs_keeps_history_and_one_input_line(self):
        self.app.append_log('Connected\n')
        self.text.tag_add('sel', '1.0', 'end-1c')
        self.text.mark_set('insert', '1.0')
        with patch.object(self.root, 'clipboard_get', return_value='MODEL\r\n123'):
            self.assertEqual(self.app.paste_model(), 'break')
        self.assertEqual(self.text.get('1.0', 'end-1c'), 'Connected\nMODEL  123')
