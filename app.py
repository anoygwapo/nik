from flask import Flask, render_template, request, redirect, url_for, session, flash, g, jsonify
import sqlite3

app = Flask(__name__)
app.secret_key = "echoesofhope_secret"

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

    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    bio TEXT DEFAULT 'Spreading hope.',
                    avatar TEXT DEFAULT 'default-avatar.png'
                )''')

    c.execute('''CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        content TEXT NOT NULL,
        type TEXT NOT NULL CHECK (type IN ('story', 'quote')),
        original_author TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    # COMMENTS
    c.execute('''CREATE TABLE IF NOT EXISTS comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id INTEGER,
                    username TEXT,
                    text TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (post_id) REFERENCES posts(id)
                )''')

    # FOLLOWERS
    c.execute('''CREATE TABLE IF NOT EXISTS follows (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    follower TEXT NOT NULL,
                    followed TEXT NOT NULL
                )''')

    # LIKES
    c.execute('''CREATE TABLE IF NOT EXISTS likes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    FOREIGN KEY (post_id) REFERENCES posts(id)
                )''')

    conn.commit()
    conn.close()

init_db()

# ---------------- HELPER FUNCTIONS ----------------
def get_posts(post_type=None, username=None):
    conn = get_db()
    query = "SELECT * FROM posts"
    params = []

    if post_type:
        query += " WHERE type=?"
        params.append(post_type)
    if username:
        query += " AND username=?" if post_type else " WHERE username=?"
        params.append(username)

    query += " ORDER BY created_at DESC"
    posts_data = conn.execute(query, params).fetchall()
    posts = []

    for p in posts_data:
        comments = conn.execute(
            "SELECT username, text FROM comments WHERE post_id=? ORDER BY created_at", (p["id"],)
        ).fetchall()

        likes_count = conn.execute(
            "SELECT COUNT(*) FROM likes WHERE post_id=?", (p["id"],)
        ).fetchone()[0]

        posts.append({
            "id": p["id"],
            "username": p["username"],
            "type": p["type"],
            "text": p["content"],  # main post text
            "original_author": p["original_author"],

            # ✅ If the post is shared (repost), this makes the original content visible
            "original_text": p["content"] if p["original_author"] else None,

            "comments": comments,
            "likes": likes_count
        })

    return posts


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
            return redirect(url_for('home'))
        else:
            flash("Invalid credentials.", "error")
    return render_template('register.html')

# ---------- LOGOUT ----------
@app.route('/logout')
def logout():
    session.pop('username', None)
    flash("You have logged out.", "info")
    return redirect(url_for('index'))

# ---------- HOME ----------
@app.route('/home')
def home():
    if 'username' not in session:
        return redirect(url_for('login'))

    conn = get_db()
    posts = get_posts()

    # Get all users (for "People You May Know")
    users = conn.execute("SELECT id, username FROM users").fetchall()

    # Get list of who current user follows
    following_rows = conn.execute(
        "SELECT followed FROM follows WHERE follower=?", (session['username'],)
    ).fetchall()
    following = [f['followed'] for f in following_rows]

    return render_template("home.html", posts=posts, users=users, following=following)

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
    if 'username' not in session:
        flash("Please log in first.", "error")
        return redirect(url_for('login'))

    post_id = request.form.get('post_id')
    text = request.form.get('text', '').strip()

    if not text:
        flash("Comment cannot be empty.", "error")
        return redirect(url_for('home'))

    conn = get_db()
    conn.execute("INSERT INTO comments (post_id, username, text) VALUES (?, ?, ?)",
                 (post_id, session['username'], text))
    conn.commit()

    flash("Comment added!", "success")
    return redirect(url_for('home'))

# ---------- SHARE POST ----------
@app.route('/share/<int:post_id>', methods=['POST'])
def share_post(post_id):
    if 'username' not in session:
        flash("Please log in first.", "error")
        return redirect(url_for('login'))

    conn = get_db()

    # Get original post
    original = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()

    if not original:
        flash("Post not found.", "error")
        return redirect(url_for('home'))

    # Create new post under current user but keep reference to source
    conn.execute("""
        INSERT INTO posts (username, content, type, original_author)
        VALUES (?, ?, ?, ?)
    """, (
        session['username'],
        original['content'],
        original['type'],
        original['username']
    ))
    conn.commit()

    flash("Post shared to your profile!", "success")
    return redirect(url_for('home'))


# ---------- FOLLOW / UNFOLLOW ----------
@app.route('/follow/<username>', methods=['POST'])
def follow(username):
    if 'username' not in session or username == session['username']:
        return redirect(url_for('home'))

    conn = get_db()
    follower = session['username']

    existing = conn.execute(
        "SELECT * FROM follows WHERE follower=? AND followed=?",
        (follower, username)
    ).fetchone()

    if existing:
        conn.execute("DELETE FROM follows WHERE follower=? AND followed=?", (follower, username))
        flash(f"You unfollowed {username}.", "info")
    else:
        conn.execute("INSERT INTO follows (follower, followed) VALUES (?, ?)", (follower, username))
        flash(f"You followed {username}!", "success")

    conn.commit()
    return redirect(request.referrer or url_for('home'))

# ---------- PROFILE ----------
@app.route('/profile/<username>')
def profile(username):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if not user:
        flash("User not found.", "error")
        return redirect(url_for('home'))

    posts = get_posts(username=username)
    followers = conn.execute("SELECT follower FROM follows WHERE followed=?", (username,)).fetchall()
    following = conn.execute("SELECT followed FROM follows WHERE follower=?", (username,)).fetchall()

    is_following = False
    if 'username' in session:
        is_following = conn.execute(
            "SELECT 1 FROM follows WHERE follower=? AND followed=?",
            (session['username'], username)
        ).fetchone() is not None

    return render_template("profile.html", user=user, posts=posts,
                           followers=followers, following=following,
                           is_following=is_following)

# ---------- LIKE ----------
@app.route('/like/<int:post_id>', methods=['POST'])
def like(post_id):
    if 'username' not in session:
        return jsonify({'error': 'Login required'}), 403

    username = session['username']
    conn = get_db()

    existing = conn.execute(
        "SELECT * FROM likes WHERE post_id=? AND username=?",
        (post_id, username)
    ).fetchone()

    if existing:
        # Unlike
        conn.execute("DELETE FROM likes WHERE post_id=? AND username=?", (post_id, username))
    else:
        # Like
        conn.execute("INSERT INTO likes (post_id, username) VALUES (?, ?)", (post_id, username))

    conn.commit()

    # Return updated like count
    total_likes = conn.execute(
        "SELECT COUNT(*) FROM likes WHERE post_id=?", (post_id,)
    ).fetchone()[0]

    return jsonify({'likes': total_likes})

# ---------- AJAX COMMENT ----------
@app.route('/comment/<int:post_id>', methods=['POST'])
def comment(post_id):
    if 'username' not in session:
        return jsonify({'error': 'Login required'}), 403

    data = request.get_json()
    text = data.get('text', '').strip()
    if not text:
        return jsonify({'error': 'Empty comment'}), 400

    conn = get_db()
    conn.execute(
        "INSERT INTO comments (post_id, username, text) VALUES (?, ?, ?)",
        (post_id, session['username'], text)
    )
    conn.commit()

    return jsonify({'user': session['username'], 'text': text})

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
