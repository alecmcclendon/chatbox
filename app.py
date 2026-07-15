from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import sqlite3

from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, join_room, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
socketio = SocketIO(app)

JST = ZoneInfo("Asia/Tokyo")

ROOMS = [
    'メイン',
    'アニメ',
    'イラスト',
    '映画',
    '英語',
    '音楽',
    '学校',
    'ゲーム',
    '小説',
    '仕事',
    '質問',
    'スポーツ',
    '勉強',
    'ファッション',
    'プログラミング',
    'マンガ',
    '料理',
    '旅行',
    'ニュース',
]

room_users = {}
chat_history = {}
user_connections = {}


def init_db():
    with sqlite3.connect('users.db') as conn:
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        ''')
        conn.commit()


init_db()


@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        uname = request.form['username'].strip()
        pwd = request.form['password']

        with sqlite3.connect('users.db') as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT 1 FROM users WHERE username=? AND password=?",
                (uname, pwd)
            )

            if cur.fetchone():
                session['username'] = uname
                return redirect(url_for('mainchat', room='メイン'))

        return render_template(
            'index.html',
            error="ユーザー名またはパスワードが違います。"
        )

    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        uname = request.form['username'].strip()
        pwd = request.form['password']

        if not uname or not pwd:
            return render_template(
                'register.html',
                message="ユーザー名とパスワードを入力してください。"
            )

        if len(uname) > 20:
            return render_template(
                'register.html',
                message="ユーザー名は20文字以内にしてください。"
            )

        try:
            with sqlite3.connect('users.db') as conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO users (username, password) VALUES (?, ?)",
                    (uname, pwd)
                )
                conn.commit()

            return redirect(url_for('login'))

        except sqlite3.IntegrityError:
            return render_template(
                'register.html',
                message="ユーザー名はすでに使われています。"
            )

    return render_template('register.html')


@app.route('/chat/<room>')
def mainchat(room):
    if 'username' not in session:
        return redirect(url_for('login'))

    if room not in ROOMS:
        return redirect(url_for('mainchat', room='メイン'))

    return render_template(
        'mainchat.html',
        username=session['username'],
        room=room,
        rooms=ROOMS
    )


def remove_user_from_online_lists(username):
    for room_name, users in list(room_users.items()):
        if username in users:
            users.remove(username)

            socketio.emit(
                'status',
                {'msg': f"{username} left."},
                room=room_name
            )

            socketio.emit(
                'user_list',
                {'users': sorted(list(users))},
                room=room_name
            )

    user_connections.pop(username, None)


@app.route('/logout', methods=['POST'])
def logout():
    username = session.get('username')

    if username:
        remove_user_from_online_lists(username)

    session.clear()

    return jsonify({
        'ok': True,
        'redirect': url_for('login')
    })


@app.route('/change_username', methods=['POST'])
def change_username():
    if 'username' not in session:
        return jsonify({
            'ok': False,
            'message': 'ログインしていません。'
        }), 401

    data = request.get_json()

    if not data:
        return jsonify({
            'ok': False,
            'message': 'データが送信されていません。'
        }), 400

    current_username = session['username']
    new_username = data.get('new_username', '').strip()
    password = data.get('password', '')

    if not new_username or not password:
        return jsonify({
            'ok': False,
            'message': '新しいユーザー名とパスワードを入力してください。'
        }), 400

    if new_username == current_username:
        return jsonify({
            'ok': False,
            'message': '現在のユーザー名と同じです。'
        }), 400

    if len(new_username) > 20:
        return jsonify({
            'ok': False,
            'message': 'ユーザー名は20文字以内にしてください。'
        }), 400

    with sqlite3.connect('users.db') as conn:
        cur = conn.cursor()

        cur.execute(
            "SELECT 1 FROM users WHERE username=? AND password=?",
            (current_username, password)
        )

        if not cur.fetchone():
            return jsonify({
                'ok': False,
                'message': 'パスワードが違います。'
            }), 400

        cur.execute(
            "SELECT 1 FROM users WHERE username=?",
            (new_username,)
        )

        if cur.fetchone():
            return jsonify({
                'ok': False,
                'message': 'このユーザー名はすでに使われています。'
            }), 400

        try:
            cur.execute(
                "UPDATE users SET username=? WHERE username=?",
                (new_username, current_username)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            return jsonify({
                'ok': False,
                'message': 'このユーザー名はすでに使われています。'
            }), 400

    session['username'] = new_username

    for room_name, users in list(room_users.items()):
        if current_username in users:
            users.remove(current_username)
            users.add(new_username)

            socketio.emit(
                'status',
                {'msg': f"{current_username} が {new_username} にユーザー名を変更しました。"},
                room=room_name
            )

            socketio.emit(
                'user_list',
                {'users': sorted(list(users))},
                room=room_name
            )

    if current_username in user_connections:
        user_connections[new_username] = user_connections.pop(current_username)

    target_room = request.args.get('room', 'メイン')

    if target_room not in ROOMS:
        target_room = 'メイン'

    return jsonify({
        'ok': True,
        'redirect': url_for('mainchat', room=target_room)
    })


@app.route('/delete_account', methods=['POST'])
def delete_account():
    if 'username' not in session:
        return jsonify({
            'ok': False,
            'message': 'ログインしていません。'
        }), 401

    data = request.get_json()

    if not data:
        return jsonify({
            'ok': False,
            'message': 'データが送信されていません。'
        }), 400

    input_username = data.get('username', '').strip()
    input_password = data.get('password', '')

    current_username = session['username']

    if input_username != current_username:
        return jsonify({
            'ok': False,
            'message': '現在ログイン中のユーザー名と一致しません。'
        }), 400

    with sqlite3.connect('users.db') as conn:
        cur = conn.cursor()

        cur.execute(
            "SELECT 1 FROM users WHERE username=? AND password=?",
            (input_username, input_password)
        )

        if not cur.fetchone():
            return jsonify({
                'ok': False,
                'message': 'ユーザー名またはパスワードが違います。'
            }), 400

        cur.execute(
            "DELETE FROM users WHERE username=?",
            (input_username,)
        )
        conn.commit()

    remove_user_from_online_lists(input_username)
    session.clear()

    return jsonify({
        'ok': True,
        'redirect': url_for('login')
    })


@socketio.on('join')
def handle_join(data):
    username = session.get('username')
    room = data.get('room')

    if not username:
        return

    if room not in ROOMS:
        return

    join_room(room)

    already = username in room_users.get(room, set())

    room_users.setdefault(room, set()).add(username)
    user_connections[username] = request.sid

    for m in chat_history.get(room, []):
        emit('message', {
            'username': m['username'],
            'message': m['message'],
            'timestamp': m['timestamp'].isoformat()
        }, to=request.sid)

    if not already:
        emit('status', {'msg': f"{username} joined."}, room=room)

    emit(
        'user_list',
        {'users': sorted(list(room_users[room]))},
        room=room
    )


@socketio.on('text')
def handle_text(data):
    username = session.get('username')
    room = data.get('room')
    text = data.get('message', '').strip()

    if not username:
        return

    if room not in ROOMS:
        return

    if not text:
        return

    now = datetime.now(JST)

    chat_history.setdefault(room, []).append({
        'username': username,
        'message': text,
        'timestamp': now
    })

    emit('message', {
        'username': username,
        'message': text,
        'timestamp': now.isoformat()
    }, room=room)


@socketio.on('disconnect')
def handle_disconnect():
    username = session.get('username')

    if not username:
        return

    this_sid = request.sid

    def remove_if_still_gone():
        socketio.sleep(5)

        if user_connections.get(username) == this_sid:
            for room_name, users in list(room_users.items()):
                if username in users:
                    users.remove(username)

                    socketio.emit(
                        'status',
                        {'msg': f"{username} left."},
                        room=room_name
                    )

                    socketio.emit(
                        'user_list',
                        {'users': sorted(list(users))},
                        room=room_name
                    )

            user_connections.pop(username, None)

    socketio.start_background_task(remove_if_still_gone)

def clear_all_messages_at_midnight():
    while True:
        now = datetime.now(JST)
        next_midnight = (
            now.replace(hour=0, minute=0, second=0, microsecond=0)
            + timedelta(days=1)
        )
        socketio.sleep((next_midnight - now).total_seconds())
        chat_history.clear()
        socketio.emit('clear_messages')



if __name__ == '__main__':
    socketio.start_background_task(clear_all_messages_at_midnight)
    print("\n✅ Server listening on http://127.0.0.1:5001\n")
    socketio.run(
        app,
        host='0.0.0.0',
        port=5001,
        debug=True,
        use_reloader=False
    )