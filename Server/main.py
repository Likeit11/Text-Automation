import sqlite3
import re
import os
import click
import pandas as pd
import io
from flask import Flask, request, jsonify, render_template, g, redirect, url_for, send_file
from flask_socketio import SocketIO, emit
import math

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, async_mode='eventlet')

DATA_DIR = 'data'
DATABASE = os.path.join(DATA_DIR, 'database.db')
PER_PAGE = 20

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

@app.route('/', methods=['GET', 'POST'])
def index():
    init_db_if_needed()
    db = get_db()

    if request.method == 'POST':
        # This part handles the SMS submission from the Android app
        data = request.json
        sender = data.get('sender')
        message_body = data.get('message')
        if not sender or not message_body:
            return jsonify({'error': 'Missing sender or message'}), 400

        cursor = db.execute('INSERT INTO messages (sender, body) VALUES (?, ?)', (sender, message_body))
        new_message_id = cursor.lastrowid
        db.commit()

        filters = db.execute('SELECT * FROM filters').fetchall()
        match_found = False
        for f in filters:
            if (f['filter_type'] == 'keyword' and f['value'] in message_body) or \
               (f['filter_type'] == 'sender' and f['value'] == sender):
                match_found = True
                matched_filter_info = f['value']
                break
        
        if match_found:
            auth_code_match = re.search(r'(\d{6})', message_body)
            if auth_code_match:
                auth_code = auth_code_match.group(1)
                print(f"Matching code found: {auth_code}. Emitting to clients.")
                socketio.emit('new_code', {
                    'code': auth_code,
                    'filter_type': f['filter_type'],
                    'filter_value': f['value']
                })
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
def handle_connect():
    print('PC client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('PC client disconnected')

if __name__ == '__main__':
    os.makedirs(DATA_DIR, exist_ok=True)
    init_db_if_needed()
    print("Starting WebSocket server...")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
