import base64
from contextlib import closing
import importlib.util
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from urllib.parse import urlsplit, parse_qs
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'client'))
from connection_options import accepts_code, connection_urls, parse_options

os.environ['SMS_ASYNC_MODE'] = 'threading'
spec = importlib.util.spec_from_file_location('sms_server', ROOT / 'Server' / 'main.py')
server = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = server
spec.loader.exec_module(server)

KEY_A = 'Private_Test_Key_A_123456'
KEY_B = 'Private_Test_Key_B_123456'


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {'SMS_ALLOW_LEGACY': '1', 'SMS_ADMIN_TOKEN': 'test-admin'})
        self.environment.start()
        self.database = patch.object(server, 'DATABASE', str(Path(self.temp.name) / 'database.db'))
        self.database.start()
        server.app.config['TESTING'] = True
        server.init_db_if_needed()
        with server.app.app_context():
            db = server.get_db()
            db.execute("INSERT INTO filters (filter_type, value) VALUES ('keyword', '[Test]')")
            db.commit()
        self.http = server.app.test_client()
        self.clients = []

    def tearDown(self):
        for client in self.clients:
            if client.is_connected():
                client.disconnect()
        self.database.stop()
        self.environment.stop()
        self.temp.cleanup()

    def connect(self, key=None):
        auth = {'key': key} if key is not None else None
        client = server.socketio.test_client(server.app, auth=auth)
        self.clients.append(client)
        return client

    def post(self, **extra):
        return self.http.post('/', json={'sender': 'Test', 'message': '[Test] 200000', **extra})

    def codes(self, client):
        return [event['args'][0] for event in client.get_received() if event['name'] == 'new_code']

    def test_keys_are_isolated_and_same_key_fans_out(self):
        a1, a2, b, legacy = self.connect(KEY_A), self.connect(KEY_A), self.connect(KEY_B), self.connect()
        self.assertEqual(self.post(key=KEY_A).status_code, 201)
        for client in (a1, a2):
            self.assertEqual(self.codes(client), [{'code': '200000', 'filter_type': 'keyword',
                                                  'filter_value': '[Test]', 'routing': 'keyed'}])
        self.assertEqual(self.codes(b), [])
        self.assertEqual(self.codes(legacy), [])
        self.assertEqual(self.post(key=KEY_B).status_code, 201)
        self.assertEqual(len(self.codes(b)), 1)
        self.assertEqual(self.codes(a1), [])
        self.assertEqual(self.codes(a2), [])

    def test_legacy_sms_reaches_only_legacy_clients(self):
        keyed, legacy = self.connect(KEY_A), self.connect()
        self.assertEqual(self.post().status_code, 201)
        self.assertEqual(self.codes(keyed), [])
        self.assertEqual(self.codes(legacy)[0]['routing'], 'legacy')

    def test_missing_keys_can_be_disabled_without_disabling_keyed_clients(self):
        with patch.dict(os.environ, {'SMS_ALLOW_LEGACY': '0'}):
            self.assertFalse(self.connect().is_connected())
            self.assertEqual(self.post().status_code, 400)
            self.assertTrue(self.connect(KEY_A).is_connected())
            self.assertEqual(self.post(key=KEY_A).status_code, 201)

    def test_invalid_keys_never_fall_back_to_legacy(self):
        legacy = self.connect()
        for key in ('', 'abc', '가나', None, 123, [], 'x' * 129, 'spaces are forbidden', 'x' * 16 + '\n'):
            with self.subTest(key=key):
                self.assertEqual(self.post(key=key).status_code, 400)
                client = server.socketio.test_client(server.app, auth={'key': key})
                self.clients.append(client)
                self.assertFalse(client.is_connected())
        self.assertEqual(self.codes(legacy), [])
        with closing(sqlite3.connect(server.DATABASE)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM messages').fetchone()[0], 0)

    def test_reconnect_rejoins_only_the_selected_key(self):
        client = self.connect(KEY_A)
        client.disconnect()
        client.connect(auth={'key': KEY_B})
        self.assertEqual(self.post(key=KEY_A).status_code, 201)
        self.assertEqual(self.codes(client), [])
        self.assertEqual(self.post(key=KEY_B).status_code, 201)
        self.assertEqual(len(self.codes(client)), 1)

    def test_four_to_128_character_keys_are_accepted(self):
        for key in ('1234', 'abcd', '가나다라', '\U0001f600' * 4, '가' * 128):
            with self.subTest(key=key):
                client = self.connect(key)
                self.assertTrue(client.is_connected())
                self.assertEqual(self.post(key=key).status_code, 201)
                self.assertEqual(self.codes(client)[0]['code'], '200000')
                client.disconnect()

    def test_ready_event_and_capabilities_do_not_disclose_keys(self):
        events = self.connect(KEY_A).get_received()
        ready = [e['args'][0] for e in events if e['name'] == 'routing_ready']
        self.assertEqual(ready, [{'version': 1, 'mode': 'keyed'}])
        self.assertNotIn(KEY_A, str(events))
        self.assertEqual(self.http.get('/capabilities').json, {'key_routing_version': 1, 'product_search_version': 1})

    def connect_phone(self, key=KEY_A):
        client = server.socketio.test_client(server.app, auth={'key': key, 'role': 'phone'})
        self.clients.append(client)
        client.get_received()
        return client

    def test_search_reaches_only_phones_with_the_same_key(self):
        pc = self.connect(KEY_A)
        phone, other = self.connect_phone(), self.connect_phone(KEY_B)
        another_pc = self.connect(KEY_A)
        another_pc.get_received()
        result = pc.emit('open_product_search', {'model': ' MODEL 한글 &+# ', 'key': KEY_B}, callback=True)
        self.assertEqual(result, {'status': 'sent', 'phones': 1})
        events = phone.get_received()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['name'], 'open_product_search')
        url = urlsplit(events[0]['args'][0]['url'])
        self.assertEqual((url.scheme, url.netloc, url.path), ('https', '9tems.com', '/product/search.html'))
        self.assertEqual(parse_qs(url.query)['keyword'], ['MODEL 한글 &+#'])
        self.assertEqual(other.get_received(), [])
        self.assertEqual(another_pc.get_received(), [])
        with closing(sqlite3.connect(server.DATABASE)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM messages').fetchone()[0], 0)

    def test_search_fans_out_to_same_key_phones_and_reports_offline(self):
        pc = self.connect(KEY_A)
        self.assertEqual(pc.emit('open_product_search', {'model': 'MODEL'}, callback=True)['status'], 'error')
        phones = [self.connect_phone(), self.connect_phone()]
        self.assertEqual(pc.emit('open_product_search', {'model': 'MODEL'}, callback=True), {'status': 'sent', 'phones': 2})
        for phone in phones:
            self.assertEqual(len(phone.get_received()), 1)
            phone.disconnect()
        self.assertEqual(pc.emit('open_product_search', {'model': 'MODEL'}, callback=True)['status'], 'error')

    def test_search_rejects_invalid_models(self):
        pc, phone = self.connect(KEY_A), self.connect_phone()
        for data in (None, [], {}, {'model': 12}, {'model': ' '}, {'model': 'x' * 201}, {'model': 'abc\n'}):
            self.assertEqual(pc.emit('open_product_search', data, callback=True)['status'], 'error')
        self.assertEqual(phone.get_received(), [])

    def test_phones_and_legacy_clients_cannot_send_searches(self):
        phone, legacy = self.connect_phone(), self.connect()
        for client in (phone, legacy):
            self.assertEqual(client.emit('open_product_search', {'model': 'MODEL'}, callback=True)['status'], 'error')
        self.assertEqual(phone.get_received(), [])
        for auth in ({'role': 'phone'}, {'key': KEY_A, 'role': 'unknown'}):
            client = server.socketio.test_client(server.app, auth=auth)
            self.clients.append(client)
            self.assertFalse(client.is_connected())

    def test_sms_codes_are_not_sent_to_phone_command_connections(self):
        phone = self.connect_phone()
        self.assertEqual(self.post(key=KEY_A).status_code, 201)
        self.assertEqual(phone.get_received(), [])

    def test_existing_database_and_filters_survive(self):
        self.assertEqual(self.post(key=KEY_A).status_code, 201)
        with closing(sqlite3.connect(server.DATABASE)) as db:
            schema = db.execute("SELECT sql FROM sqlite_master ORDER BY name").fetchall()
        server.init_db_if_needed()
        with closing(sqlite3.connect(server.DATABASE)) as db:
            self.assertEqual(db.execute("SELECT sql FROM sqlite_master ORDER BY name").fetchall(), schema)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM filters').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT extracted_code FROM messages').fetchone()[0], '200000')
        self.assertNotIn(KEY_A.encode(), Path(server.DATABASE).read_bytes())

    def test_invalid_json_and_non_text_messages_are_rejected(self):
        for value in ([], None, {'key': KEY_A, 'sender': 1, 'message': 'text'},
                      {'key': KEY_A, 'sender': 'Test', 'message': []}):
            self.assertEqual(self.http.post('/', json=value).status_code, 400)

    def test_nonmatching_sms_is_not_stored_or_emitted(self):
        keyed, legacy = self.connect(KEY_A), self.connect()
        for extra in ({'key': KEY_A}, {}):
            response = self.http.post('/', json={'sender': 'Test', 'message': 'Other 200000', **extra})
            self.assertEqual(response.status_code, 201)
        self.assertEqual(self.codes(keyed), [])
        self.assertEqual(self.codes(legacy), [])
        with closing(sqlite3.connect(server.DATABASE)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM messages').fetchone()[0], 0)
        self.assertNotIn(b'Other 200000', Path(server.DATABASE).read_bytes())

    def test_no_filters_discards_sms(self):
        with closing(sqlite3.connect(server.DATABASE)) as db:
            db.execute('DELETE FROM filters')
            db.commit()
        self.assertEqual(self.post(key=KEY_A).status_code, 201)
        with closing(sqlite3.connect(server.DATABASE)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM messages').fetchone()[0], 0)

    def test_matching_sender_is_stored_and_emitted(self):
        with closing(sqlite3.connect(server.DATABASE)) as db:
            db.execute("INSERT INTO filters (filter_type, value) VALUES ('sender', 'Trusted')")
            db.commit()
        client = self.connect(KEY_A)
        response = self.http.post('/', json={'sender': 'Trusted', 'message': 'Other 200000', 'key': KEY_A})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.codes(client)[0]['code'], '200000')
        with closing(sqlite3.connect(server.DATABASE)) as db:
            self.assertEqual(db.execute('SELECT body, processed FROM messages').fetchone(), ('Other 200000', 1))

    def test_matching_sms_without_code_is_stored_but_not_emitted(self):
        client = self.connect(KEY_A)
        response = self.http.post('/', json={'sender': 'Test', 'message': '[Test] no code', 'key': KEY_A})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.codes(client), [])
        with closing(sqlite3.connect(server.DATABASE)) as db:
            self.assertEqual(db.execute('SELECT body, processed FROM messages').fetchone(), ('[Test] no code', 0))

    def test_dashboard_export_and_mutations_require_admin_credentials(self):
        for path, method in (('/', 'get'), ('/export', 'get'), ('/add_filter', 'post'),
                             ('/delete_filter/1', 'post'), ('/delete', 'post')):
            with self.subTest(path=path):
                self.assertEqual(getattr(self.http, method)(path).status_code, 401)
        for password in (KEY_A, 'wrong'):
            auth = base64.b64encode(('admin:' + password).encode()).decode()
            self.assertEqual(self.http.get('/', headers={'Authorization': 'Basic ' + auth}).status_code, 401)
        auth = base64.b64encode(b'admin:test-admin').decode()
        self.assertEqual(self.http.get('/', headers={'Authorization': 'Basic ' + auth}).status_code, 200)
        with patch.dict(os.environ, {'SMS_ADMIN_TOKEN': ''}):
            self.assertEqual(self.http.get('/').status_code, 503)


class ClientOptionsTests(unittest.TestCase):
    def test_separator_and_positional_key(self):
        self.assertEqual(parse_options(['--', KEY_A]).key, KEY_A)
        self.assertEqual(parse_options([KEY_A]).key, KEY_A)
        self.assertEqual(parse_options(['--', '-' + KEY_A]).key, '-' + KEY_A)
        self.assertIsNone(parse_options(['--legacy']).key)

    def test_missing_invalid_and_conflicting_options(self):
        for args in ([], ['--'], ['abc'], ['가나'], ['--legacy', KEY_A], ['--', 'x' * 129],
                     ['--', 'a' * 16 + '\n'], ['--unknown'], ['--key', KEY_A], [KEY_A, KEY_A]):
            with self.subTest(args=args):
                options = parse_options(args)
                self.assertIsNone(options.key)
                self.assertTrue(options.legacy)

    def test_four_to_128_character_keys_are_accepted(self):
        for key in ('1234', 'abcd', '가나다라', '\U0001f600' * 4, '가' * 128):
            with self.subTest(key=key):
                self.assertEqual(parse_options(['--', key]).key, key)

    def test_keyed_mode_never_uses_http_fallback(self):
        urls = ['https://example.com', 'http://127.0.0.1:8312', '']
        self.assertEqual(connection_urls(urls, KEY_A), urls[:1])
        self.assertEqual(connection_urls(urls, None), urls[:2])

    def test_keyed_mode_ignores_old_broadcasts_and_unconfirmed_connections(self):
        self.assertFalse(accepts_code({'code': '200000'}, KEY_A, False))
        self.assertFalse(accepts_code({'code': '200000'}, KEY_A, True))
        self.assertFalse(accepts_code({'routing': 'keyed'}, KEY_A, False))
        self.assertFalse(accepts_code({'routing': 'legacy'}, KEY_A, True))
        self.assertTrue(accepts_code({'routing': 'keyed'}, KEY_A, True))
        self.assertTrue(accepts_code({'code': '200000'}, None, False))


if __name__ == '__main__':
    unittest.main()
