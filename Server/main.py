import sqlite3
import re
import os
import hashlib
import hmac
import click
import pandas as pd
import io
from flask import Flask, request, jsonify, render_template, g, redirect, url_for, send_file
from flask_socketio import SocketIO, emit, join_room
import math
from urllib.parse import urlencode
from flask import session

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, async_mode=os.environ.get('SMS_ASYNC_MODE', 'eventlet'))

DATA_DIR = 'data'
DATABASE = os.path.join(DATA_DIR, 'database.db')
PER_PAGE = 20


def delivery_room(data):
    if 'key' not in data:
        if os.environ.get('SMS_ALLOW_LEGACY', '1') != '1':
            raise ValueError('A pairing key is required')
        return 'legacy'
    key = data['key']
    if (not isinstance(key, str) or not 4 <= len(key) <= 128
            or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in key)):
        raise ValueError('Key must be 4-128 characters without spaces or control characters')
    return 'key:' + hashlib.sha256(key.encode('utf-8')).hexdigest()


@app.before_request
def protect_dashboard():
    if request.endpoint not in {'index', 'add_filter', 'delete_filter', 'delete_messages', 'export_excel'}:
        return
    if request.endpoint == 'index' and request.method == 'POST':
        return
    token = os.environ.get('SMS_ADMIN_TOKEN', '')
    if not token:
        return jsonify({'error': 'Set SMS_ADMIN_TOKEN to enable the admin dashboard'}), 503
    auth = request.authorization
    if (not auth or auth.type != 'basic' or auth.username != 'admin'
            or not hmac.compare_digest((auth.password or '').encode('utf-8'), token.encode('utf-8'))):
        return jsonify({'error': 'Admin authentication required'}), 401, {
            'WWW-Authenticate': 'Basic realm="SMS Admin"'
        }

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        with app.open_resource('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()

@click.command('init-db')
def init_db_command():
    init_db()
    click.echo('Initialized the database.')

app.cli.add_command(init_db_command)

def init_db_if_needed():
    if not os.path.exists(DATABASE):
        with app.app_context():
            init_db()
            print("Initialized the database.")


@app.route('/capabilities')
def capabilities():
    return jsonify({'key_routing_version': 1, 'product_search_version': 1})

@app.route('/', methods=['GET', 'POST'])
def index():
    init_db_if_needed()
    db = get_db()

    if request.method == 'POST':
        # This part handles the SMS submission from the Android app
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({'error': 'Expected a JSON object'}), 400
        try:
            room = delivery_room(data)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
        sender = data.get('sender')
        message_body = data.get('message')
        if not isinstance(sender, str) or not sender or not isinstance(message_body, str) or not message_body:
            return jsonify({'error': 'Missing sender or message'}), 400

        filters = db.execute('SELECT * FROM filters').fetchall()
        match_found = False
        for f in filters:
            if (f['filter_type'] == 'keyword' and f['value'] in message_body) or \
               (f['filter_type'] == 'sender' and f['value'] == sender):
                match_found = True
                matched_filter_info = f['value']
                break
        
        if not match_found:
            return jsonify({'status': 'success'}), 201

        cursor = db.execute('INSERT INTO messages (sender, body) VALUES (?, ?)', (sender, message_body))
        new_message_id = cursor.lastrowid
        db.commit()

        auth_code_match = re.search(r'(\d{6})', message_body)
        if auth_code_match:
            auth_code = auth_code_match.group(1)
            socketio.emit('new_code', {
                'code': auth_code,
                'filter_type': f['filter_type'],
                'filter_value': f['value'],
                'routing': 'legacy' if room == 'legacy' else 'keyed'
            }, to=room)
            db.execute('''UPDATE messages SET processed = 1, matched_filter = ?, extracted_code = ? WHERE id = ?''',
                       (matched_filter_info, auth_code, new_message_id))
            db.commit()

        return jsonify({'status': 'success'}), 201

    # This part handles displaying the web dashboard
    page = request.args.get('page', 1, type=int)
    
    # Filtering logic
    base_query = "SELECT * FROM messages"
    count_query = "SELECT COUNT(id) FROM messages"
    where_clauses = []
    params = []

    filter_processed = request.args.get('filter_processed', '')
    if filter_processed in ['0', '1']:
        where_clauses.append("processed = ?")
        params.append(filter_processed)

    filter_content = request.args.get('filter_content', '')
    if filter_content:
        where_clauses.append("(sender LIKE ? OR body LIKE ? OR matched_filter LIKE ?)")
        term = f'%{filter_content}%'
        params.extend([term, term, term])

    if where_clauses:
        query_filter_string = " WHERE " + " AND ".join(where_clauses)
        base_query += query_filter_string
        count_query += query_filter_string

    # Sorting logic is now fixed to show most recent first
    base_query += " ORDER BY timestamp DESC"

    # Pagination logic
    total_messages = db.execute(count_query, tuple(params)).fetchone()[0]
    total_pages = math.ceil(total_messages / PER_PAGE)
    offset = (page - 1) * PER_PAGE
    base_query += f" LIMIT {PER_PAGE} OFFSET {offset}"
    
    messages = db.execute(base_query, tuple(params)).fetchall()
    filters = db.execute('SELECT * FROM filters ORDER BY id DESC').fetchall()
    
    return render_template('index.html', filters=filters, messages=messages, 
                           page=page, total_pages=total_pages, args=request.args)

@app.route('/add_filter', methods=['POST'])
def add_filter():
    db = get_db()
    db.execute('INSERT INTO filters (filter_type, value) VALUES (?, ?)', 
               (request.form['filter_type'], request.form['value']))
    db.commit()
    return redirect(url_for('index'))

@app.route('/delete_filter/<int:filter_id>', methods=['POST'])
def delete_filter(filter_id):
    db = get_db()
    db.execute('DELETE FROM filters WHERE id = ?', (filter_id,))
    db.commit()
    return redirect(url_for('index'))

@app.route('/delete', methods=['POST'])
def delete_messages():
    message_ids = request.form.getlist('message_ids')
    if message_ids:
        db = get_db()
        placeholders = ', '.join('?' for _ in message_ids)
        db.execute(f'DELETE FROM messages WHERE id IN ({placeholders})', tuple(message_ids))
        db.commit()
    return redirect(url_for('index', **request.args))

@app.route('/export')
def export_excel():
    db = get_db()
    # This export function can be expanded to use the same filtering logic as the index page
    query = "SELECT id, timestamp, sender, body, processed, matched_filter, extracted_code FROM messages ORDER BY timestamp DESC"
    df = pd.read_sql_query(query, db)
    
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='openpyxl')
    df.to_excel(writer, index=False, sheet_name='Messages')
    writer.close()
    output.seek(0)
    
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 
                     as_attachment=True, download_name='messages.xlsx')

@socketio.on('connect')
def handle_connect(auth=None):
    if auth is not None and not isinstance(auth, dict):
        return False
    try:
        room = delivery_room(auth if auth is not None else {})
    except ValueError:
        return False
    role = auth.get('role', 'pc') if auth is not None else 'pc'
    if role not in ('pc', 'phone') or (role == 'phone' and room == 'legacy'):
        return False
    session['pairing_room'] = room
    session['device_role'] = role
    join_room('phone:' + room if role == 'phone' else room)
    ready = {'version': 1, 'mode': 'legacy' if room == 'legacy' else 'keyed'}
    if role == 'phone':
        ready['role'] = 'phone'
    emit('routing_ready', ready)
    print('PC client connected')

@socketio.on('open_product_search')
def open_product_search(data):
    room = session.get('pairing_room', '')
    if session.get('device_role') != 'pc' or not room.startswith('key:'):
        return {'status': 'error', 'error': 'A paired PC connection is required.'}
    model = data.get('model') if isinstance(data, dict) else None
    if (not isinstance(model, str) or not 1 <= len(model.strip()) <= 200
            or any(ord(c) < 32 or ord(c) == 127 for c in model)):
        return {'status': 'error', 'error': 'Enter a model name of 1-200 characters.'}
    phone_room = 'phone:' + room
    phones = len(list(socketio.server.manager.get_participants('/', phone_room)))
    if not phones:
        return {'status': 'error', 'error': 'No phone is connected with this pairing key.'}
    url = 'https://9tems.com/product/search.html?' + urlencode({'banner_action': '', 'keyword': model.strip()})
    socketio.emit('open_product_search', {'url': url}, to=phone_room)
    return {'status': 'sent', 'phones': phones}

@socketio.on('disconnect')
def handle_disconnect(reason=None):
    print('PC client disconnected')

if __name__ == '__main__':
    if os.environ.get('SMS_REQUIRE_EXISTING_DB') == '1' and (
        not os.path.ismount(DATA_DIR) or not os.path.isfile(DATABASE)
    ):
        raise RuntimeError('SMS database mount or database.db is missing')
    os.makedirs(DATA_DIR, exist_ok=True)
    init_db_if_needed()
    print("Starting WebSocket server...")
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
