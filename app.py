import os
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
DB_PATH = BASE_DIR / "photo_booth.db"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", secrets.token_hex(16))
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (event_id) REFERENCES events(id)
        );
        """
    )
    db.commit()


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def ensure_event_dir(slug: str) -> Path:
    event_dir = UPLOAD_DIR / slug
    event_dir.mkdir(parents=True, exist_ok=True)
    return event_dir


def require_admin() -> bool:
    return bool(session.get("admin"))


def save_photo(event: sqlite3.Row, file_storage) -> None:
    if not file_storage or not file_storage.filename:
        return

    if not allowed_file(file_storage.filename):
        raise ValueError("Unsupported file type")

    safe_name = secure_filename(file_storage.filename)
    ext = Path(safe_name).suffix.lower()
    unique_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}{ext}"
    event_dir = ensure_event_dir(event["slug"])
    file_storage.save(event_dir / unique_name)

    db = get_db()
    db.execute(
        "INSERT INTO photos(event_id, filename, created_at) VALUES (?, ?, ?)",
        (event["id"], unique_name, datetime.utcnow().isoformat()),
    )
    db.commit()


def get_event_by_slug(slug: str):
    db = get_db()
    return db.execute("SELECT * FROM events WHERE slug = ?", (slug,)).fetchone()


def list_photos(event_id: int):
    db = get_db()
    return db.execute(
        "SELECT * FROM photos WHERE event_id = ? ORDER BY created_at DESC", (event_id,)
    ).fetchall()


@app.before_request
def bootstrap():
    UPLOAD_DIR.mkdir(exist_ok=True)
    init_db()


@app.route("/")
def home():
    db = get_db()
    events = db.execute("SELECT * FROM events ORDER BY created_at DESC").fetchall()
    return render_template("home.html", events=events)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == os.environ.get("ADMIN_PASSWORD", "admin123"):
            session["admin"] = True
            flash("Logged in as admin.", "success")
            return redirect(url_for("admin_dashboard"))
        flash("Invalid password.", "error")

    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for("home"))


@app.route("/admin", methods=["GET", "POST"])
def admin_dashboard():
    if not require_admin():
        return redirect(url_for("admin_login"))

    db = get_db()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Event name is required.", "error")
        else:
            base_slug = secure_filename(name).replace("_", "-").lower() or "event"
            slug = base_slug
            i = 2
            while db.execute("SELECT id FROM events WHERE slug = ?", (slug,)).fetchone():
                slug = f"{base_slug}-{i}"
                i += 1
            db.execute(
                "INSERT INTO events(name, slug, created_at) VALUES (?, ?, ?)",
                (name, slug, datetime.utcnow().isoformat()),
            )
            db.commit()
            flash(f"Event '{name}' created.", "success")

    events = db.execute("SELECT * FROM events ORDER BY created_at DESC").fetchall()
    base_url = request.url_root.rstrip("/")
    return render_template("admin_dashboard.html", events=events, base_url=base_url)


@app.route("/admin/event/<slug>", methods=["GET", "POST"])
def admin_event(slug: str):
    if not require_admin():
        return redirect(url_for("admin_login"))

    event = get_event_by_slug(slug)
    if not event:
        return "Event not found", 404

    if request.method == "POST":
        files = request.files.getlist("photos")
        uploaded = 0
        for f in files:
            if f and f.filename:
                save_photo(event, f)
                uploaded += 1
        flash(f"Uploaded {uploaded} photos.", "success")

    photos = list_photos(event["id"])
    return render_template("admin_event.html", event=event, photos=photos)


@app.route("/e/<slug>", methods=["GET", "POST"])
def event_capture(slug: str):
    event = get_event_by_slug(slug)
    if not event:
        return "Event not found", 404

    if request.method == "POST":
        file = request.files.get("photo")
        if not file or not file.filename:
            flash("Please pick a photo first.", "error")
        else:
            try:
                save_photo(event, file)
                flash("Photo uploaded. Thank you!", "success")
            except ValueError as exc:
                flash(str(exc), "error")

    photos_count = get_db().execute(
        "SELECT COUNT(*) AS c FROM photos WHERE event_id = ?", (event["id"],)
    ).fetchone()["c"]
    return render_template("event_capture.html", event=event, photos_count=photos_count)


@app.route("/display/<slug>")
def event_display(slug: str):
    event = get_event_by_slug(slug)
    if not event:
        return "Event not found", 404

    photos = list_photos(event["id"])
    return render_template("display.html", event=event, photos=photos)


@app.route("/uploads/<slug>/<filename>")
def uploads(slug: str, filename: str):
    return send_from_directory(UPLOAD_DIR / slug, filename)


if __name__ == "__main__":
    UPLOAD_DIR.mkdir(exist_ok=True)
    with app.app_context():
        init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
