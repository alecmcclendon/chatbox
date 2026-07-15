from datetime import datetime, timedelta
from threading import RLock
from zoneinfo import ZoneInfo
import os
import sqlite3

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import check_password_hash, generate_password_hash


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY",
    "local-development-key-change-this",
)

# The threaded mode works with Render's recommended Gunicorn setup:
# gunicorn -w 1 --threads 100 app:app
socketio = SocketIO(app, async_mode="threading")

JST = ZoneInfo("Asia/Tokyo")
DB_PATH = os.environ.get("DB_PATH", "users.db")

ROOMS = [
    "メイン",
    "アニメ",
    "イラスト",
    "映画",
    "英語",
    "音楽",
    "学校",
    "ゲーム",
    "小説",
    "仕事",
    "質問",
    "スポーツ",
    "勉強",
    "ファッション",
    "プログラミング",
    "マンガ",
    "料理",
    "旅行",
    "ニュース",
]

# room_connections:
# {
#     "room name": {
#         "socket id": "username",
#     }
# }
room_connections = {}

# socket_memberships:
# {
#     "socket id": {
#         "username": "name",
#         "room": "room name",
#     }
# }
socket_memberships = {}

chat_history = {}
presence_lock = RLock()


def get_db_connection():
    """Create a SQLite connection with sensible settings."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with get_db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
            """
        )
        conn.commit()


def verify_password(stored_password, submitted_password):
    """
    Verify both modern password hashes and old plain-text passwords.

    Old plain-text passwords are supported temporarily so existing local
    accounts do not immediately stop working after this upgrade.
    """
    if stored_password.startswith(("pbkdf2:", "scrypt:")):
        return check_password_hash(stored_password, submitted_password)

    return stored_password == submitted_password


def find_user(username):
    with get_db_connection() as conn:
        return conn.execute(
            "SELECT id, username, password FROM users WHERE username=?",
            (username,),
        ).fetchone()


def authenticate_user(username, password):
    user = find_user(username)

    if not user or not verify_password(user[2], password):
        return False

    # Automatically replace an old plain-text password with a secure hash.
    if not user[2].startswith(("pbkdf2:", "scrypt:")):
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE users SET password=? WHERE id=?",
                (generate_password_hash(password), user[0]),
            )
            conn.commit()

    return True


def get_room_usernames(room):
    """Return each online username once, even if they have multiple tabs."""
    with presence_lock:
        usernames = set(room_connections.get(room, {}).values())

    return sorted(usernames)


def broadcast_user_list(room):
    """Send the latest online-user list to everyone currently in a room."""
    socketio.emit(
        "user_list",
        {"users": get_room_usernames(room)},
        room=room,
    )


def add_socket_to_room(sid, username, room):
    """
    Record one socket as being in exactly one room.

    Returns True when this is the username's first active socket in the room.
    """
    with presence_lock:
        connections = room_connections.setdefault(room, {})
        username_already_present = username in connections.values()

        connections[sid] = username
        socket_memberships[sid] = {
            "username": username,
            "room": room,
        }

    return not username_already_present


def remove_socket_membership(sid, announce=True):
    """
    Remove one socket from its room.

    The username disappears only after its final tab/socket leaves that room.
    Returns the removed membership, or None when the socket was not tracked.
    """
    with presence_lock:
        membership = socket_memberships.pop(sid, None)

        if not membership:
            return None

        username = membership["username"]
        room = membership["room"]
        connections = room_connections.get(room)

        if connections is not None:
            connections.pop(sid, None)
            username_still_present = username in connections.values()

            if not connections:
                room_connections.pop(room, None)
        else:
            username_still_present = False

    if announce and not username_still_present:
        socketio.emit(
            "status",
            {"msg": f"{username} left."},
            room=room,
        )

    broadcast_user_list(room)
    return membership


def remove_user_from_online_lists(username, disconnect_sockets=False):
    """Remove all sockets belonging to a username from every room."""
    with presence_lock:
        matching_sids = [
            sid
            for sid, membership in socket_memberships.items()
            if membership["username"] == username
        ]

    affected_rooms = set()

    for sid in matching_sids:
        membership = remove_socket_membership(sid, announce=False)
        if membership:
            affected_rooms.add(membership["room"])

    for room in affected_rooms:
        socketio.emit(
            "status",
            {"msg": f"{username} left."},
            room=room,
        )
        broadcast_user_list(room)

    if disconnect_sockets:
        for sid in matching_sids:
            try:
                socketio.server.disconnect(sid, namespace="/")
            except Exception:
                # A tab may already have disconnected naturally.
                pass


def rename_online_user(current_username, new_username):
    """Update the username attached to every active socket."""
    affected_rooms = set()

    with presence_lock:
        for sid, membership in socket_memberships.items():
            if membership["username"] != current_username:
                continue

            room = membership["room"]
            membership["username"] = new_username

            connections = room_connections.get(room)
            if connections and sid in connections:
                connections[sid] = new_username

            affected_rooms.add(room)

    for room in affected_rooms:
        socketio.emit(
            "status",
            {
                "msg": (
                    f"{current_username} が {new_username} に"
                    "ユーザー名を変更しました。"
                )
            },
            room=room,
        )
        broadcast_user_list(room)


init_db()


@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        uname = request.form.get("username", "").strip()
        pwd = request.form.get("password", "")

        if authenticate_user(uname, pwd):
            session["username"] = uname
            return redirect(url_for("mainchat", room="メイン"))

        return render_template(
            "index.html",
            error="ユーザー名またはパスワードが違います。",
        )

    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        uname = request.form.get("username", "").strip()
        pwd = request.form.get("password", "")

        if not uname or not pwd:
            return render_template(
                "register.html",
                message="ユーザー名とパスワードを入力してください。",
            )

        if len(uname) > 20:
            return render_template(
                "register.html",
                message="ユーザー名は20文字以内にしてください。",
            )

        try:
            with get_db_connection() as conn:
                conn.execute(
                    "INSERT INTO users (username, password) VALUES (?, ?)",
                    (uname, generate_password_hash(pwd)),
                )
                conn.commit()

            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            return render_template(
                "register.html",
                message="ユーザー名はすでに使われています。",
            )

    return render_template("register.html")


@app.route("/chat/<room>")
def mainchat(room):
    if "username" not in session:
        return redirect(url_for("login"))

    if room not in ROOMS:
        return redirect(url_for("mainchat", room="メイン"))

    return render_template(
        "mainchat.html",
        username=session["username"],
        room=room,
        rooms=ROOMS,
    )


@app.route("/logout", methods=["POST"])
def logout():
    username = session.get("username")

    if username:
        remove_user_from_online_lists(username, disconnect_sockets=True)

    session.clear()

    return jsonify(
        {
            "ok": True,
            "redirect": url_for("login"),
        }
    )


@app.route("/change_username", methods=["POST"])
def change_username():
    if "username" not in session:
        return jsonify(
            {
                "ok": False,
                "message": "ログインしていません。",
            }
        ), 401

    data = request.get_json(silent=True)

    if not data:
        return jsonify(
            {
                "ok": False,
                "message": "データが送信されていません。",
            }
        ), 400

    current_username = session["username"]
    new_username = data.get("new_username", "").strip()
    password = data.get("password", "")

    if not new_username or not password:
        return jsonify(
            {
                "ok": False,
                "message": "新しいユーザー名とパスワードを入力してください。",
            }
        ), 400

    if new_username == current_username:
        return jsonify(
            {
                "ok": False,
                "message": "現在のユーザー名と同じです。",
            }
        ), 400

    if len(new_username) > 20:
        return jsonify(
            {
                "ok": False,
                "message": "ユーザー名は20文字以内にしてください。",
            }
        ), 400

    if not authenticate_user(current_username, password):
        return jsonify(
            {
                "ok": False,
                "message": "パスワードが違います。",
            }
        ), 400

    try:
        with get_db_connection() as conn:
            existing_user = conn.execute(
                "SELECT 1 FROM users WHERE username=?",
                (new_username,),
            ).fetchone()

            if existing_user:
                return jsonify(
                    {
                        "ok": False,
                        "message": "このユーザー名はすでに使われています。",
                    }
                ), 400

            conn.execute(
                "UPDATE users SET username=? WHERE username=?",
                (new_username, current_username),
            )
            conn.commit()

    except sqlite3.IntegrityError:
        return jsonify(
            {
                "ok": False,
                "message": "このユーザー名はすでに使われています。",
            }
        ), 400

    session["username"] = new_username
    rename_online_user(current_username, new_username)

    target_room = request.args.get("room", "メイン")

    if target_room not in ROOMS:
        target_room = "メイン"

    return jsonify(
        {
            "ok": True,
            "redirect": url_for("mainchat", room=target_room),
        }
    )


@app.route("/delete_account", methods=["POST"])
def delete_account():
    if "username" not in session:
        return jsonify(
            {
                "ok": False,
                "message": "ログインしていません。",
            }
        ), 401

    data = request.get_json(silent=True)

    if not data:
        return jsonify(
            {
                "ok": False,
                "message": "データが送信されていません。",
            }
        ), 400

    input_username = data.get("username", "").strip()
    input_password = data.get("password", "")
    current_username = session["username"]

    if input_username != current_username:
        return jsonify(
            {
                "ok": False,
                "message": "現在ログイン中のユーザー名と一致しません。",
            }
        ), 400

    if not authenticate_user(input_username, input_password):
        return jsonify(
            {
                "ok": False,
                "message": "ユーザー名またはパスワードが違います。",
            }
        ), 400

    with get_db_connection() as conn:
        conn.execute(
            "DELETE FROM users WHERE username=?",
            (input_username,),
        )
        conn.commit()

    remove_user_from_online_lists(input_username, disconnect_sockets=True)
    session.clear()

    return jsonify(
        {
            "ok": True,
            "redirect": url_for("login"),
        }
    )


@socketio.on("join")
def handle_join(data):
    username = session.get("username")
    room = data.get("room") if data else None
    sid = request.sid

    if not username or room not in ROOMS:
        return

    with presence_lock:
        previous = socket_memberships.get(sid)
        previous = previous.copy() if previous else None

    # A single Socket.IO connection can only belong to one chat room here.
    if previous and previous["room"] != room:
        old_room = previous["room"]
        leave_room(old_room)
        remove_socket_membership(sid)

    elif previous and previous["room"] == room:
        # Ignore duplicate join events, but refresh this tab's user list.
        emit(
            "user_list",
            {"users": get_room_usernames(room)},
            to=sid,
        )
        return

    join_room(room)
    first_socket_for_user = add_socket_to_room(sid, username, room)

    for message in chat_history.get(room, []):
        emit(
            "message",
            {
                "username": message["username"],
                "message": message["message"],
                "timestamp": message["timestamp"].isoformat(),
            },
            to=sid,
        )

    if first_socket_for_user:
        emit(
            "status",
            {"msg": f"{username} joined."},
            room=room,
        )

    broadcast_user_list(room)


@socketio.on("leave")
def handle_leave(data=None):
    sid = request.sid

    with presence_lock:
        membership = socket_memberships.get(sid)
        membership = membership.copy() if membership else None

    if not membership:
        return

    leave_room(membership["room"])
    remove_socket_membership(sid)


@socketio.on("text")
def handle_text(data):
    username = session.get("username")
    requested_room = data.get("room") if data else None
    text = data.get("message", "").strip() if data else ""

    if not username or requested_room not in ROOMS or not text:
        return

    with presence_lock:
        membership = socket_memberships.get(request.sid)
        membership = membership.copy() if membership else None

    # Do not trust a room name supplied by a stale or modified browser tab.
    if (
        not membership
        or membership["username"] != username
        or membership["room"] != requested_room
    ):
        return

    now = datetime.now(JST)

    chat_history.setdefault(requested_room, []).append(
        {
            "username": username,
            "message": text,
            "timestamp": now,
        }
    )

    emit(
        "message",
        {
            "username": username,
            "message": text,
            "timestamp": now.isoformat(),
        },
        room=requested_room,
    )


@socketio.on("disconnect")
def handle_disconnect():
    # Immediate cleanup makes room changes feel responsive. If another tab for
    # the same user remains in the room, the username stays in the list.
    remove_socket_membership(request.sid)


def clear_all_messages_at_midnight():
    while True:
        now = datetime.now(JST)
        next_midnight = (
            now.replace(hour=0, minute=0, second=0, microsecond=0)
            + timedelta(days=1)
        )
        socketio.sleep((next_midnight - now).total_seconds())
        chat_history.clear()
        socketio.emit("clear_messages")


socketio.start_background_task(clear_all_messages_at_midnight)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

    print(f"\n✅ Server listening on http://127.0.0.1:{port}\n")
    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=debug,
        use_reloader=False,
        allow_unsafe_werkzeug=True,
    )
