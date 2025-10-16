from flask import Flask, render_template, request, redirect, url_for, session, flash, g
import sqlite3
import os

app = Flask(__name__)
app.secret_key = "echoesofhope_secret"

# ---------------- DATABASE CONFIG ----------------
DATABASE = "echoes.db"

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    # Create tables
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL
                )''')

    c.execute('''CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    content TEXT NOT NULL,
                    type TEXT NOT NULL CHECK (type IN ('story', 'quote')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')

    c.execute('''CREATE TABLE IF NOT EXISTS comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id INTEGER,
                    username TEXT,
                    text TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (post_id) REFERENCES posts(id)
                )''')

    conn.commit()
    conn.close()

# Initialize the database if missing
if not os.path.exists(DATABASE):
    init_db()

# ---------------- ROUTES ----------------
@app.route('/')
def index():
    return render_template('index.html')

# ---------- REGISTER ----------
@app.route('/register', methods=['GET', 'POST'])
def register():
    conn = get_db()

    if request.method == 'POST' and 'confirm_password' in request.form:
        username = request.form['username']
        password = request.form['password']
        confirm = request.form['confirm_password']

        if password != confirm:
            flash("Passwords do not match.", "error")
            return redirect(url_for('register'))

        try:
            conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            conn.commit()
            flash("Registration successful! You can now log in.", "success")
        except sqlite3.IntegrityError:
            flash("Username already taken.", "error")

        return redirect(url_for('register'))

    return render_template('register.html')

# ---------- LOGIN ----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    conn = get_db()
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = conn.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password)).fetchone()

        if user:
            session['username'] = user['username']
            flash(f"Welcome, {username}!", "success")
            return redirect(url_for('home'))
        else:
            flash("Invalid username or password.", "error")

    return render_template('register.html')

# ---------- LOGOUT ----------
@app.route('/logout')
def logout():
    session.pop('username', None)
    flash("You have logged out.", "info")
    return redirect(url_for('index'))

# ---------- HELPER: FETCH POSTS + COMMENTS ----------
def get_posts(post_type=None):
    conn = get_db()
    if post_type:
        posts_data = conn.execute(
            "SELECT * FROM posts WHERE type=? ORDER BY created_at DESC", (post_type,)
        ).fetchall()
    else:
        posts_data = conn.execute(
            "SELECT * FROM posts ORDER BY created_at DESC"
        ).fetchall()

    posts = []
    for p in posts_data:
        comments = conn.execute(
            "SELECT username, text FROM comments WHERE post_id=? ORDER BY created_at",
            (p['id'],)
        ).fetchall()
        posts.append({
            "id": p['id'],
            "username": p['username'],
            "type": p['type'],
            "text": p['content'],
            "comments": comments
        })
    return posts

# ---------- HOME ----------
@app.route('/home')
def home():
    if 'username' not in session:
        return redirect(url_for('login'))

    profile = {
        "username": session['username'],
        "avatar": "default-avatar.png",
        "bio": "Spreading hope through stories and quotes.",
        "birthday": "January 1, 2000",
        "topics": ["Motivation", "Love", "Faith"],
        "account_type": "Writer"
    }

    posts = get_posts()
    return render_template("home.html", posts=posts, profile=profile)

# ---------- CREATE POST ----------
@app.route('/create_post', methods=['POST'])
def create_post():
    if 'username' not in session:
        flash("Please log in first.", "error")
        return redirect(url_for('login'))

    post_type = request.form.get('type')
    text = request.form.get('text', '').strip()

    if not text:
        flash("Post cannot be empty.", "error")
        return redirect(url_for('home'))

    conn = get_db()
    conn.execute("INSERT INTO posts (username, content, type) VALUES (?, ?, ?)",
                 (session['username'], text, post_type))
    conn.commit()

    flash(f"Your {post_type} has been shared!", "success")
    return redirect(url_for('home'))

# ---------- COMMENT ----------
@app.route('/post_comment', methods=['POST'])
def post_comment():
    post_id = request.form.get('post_id')
    username = request.form.get('username')
    text = request.form.get('text', '').strip()

    if not text:
        flash("Comment cannot be empty.", "error")
        return redirect(url_for('home'))

    conn = get_db()
    conn.execute("INSERT INTO comments (post_id, username, text) VALUES (?, ?, ?)",
                 (post_id, username, text))
    conn.commit()

    flash("Comment added!", "success")
    return redirect(url_for('home'))

# ---------- STORIES ----------
@app.route('/stories')
def stories():
    posts = get_posts("story")
    return render_template('stories.html', posts=posts)

# ---------- QUOTES ----------
@app.route('/quotes')
def quotes():
    posts = get_posts("quote")
    return render_template('quotes.html', posts=posts)

# ---------- RUN ----------
if __name__ == '__main__':
    app.run(debug=True)
