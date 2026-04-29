import os
import calendar
import json
import sqlite3
from datetime import date, timedelta
from functools import wraps

from flask import Flask, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "database.db")
REMINDERS_FILE = os.path.join(BASE_DIR, "habit_reminders.json")

app = Flask(__name__)
app.config["SECRET_KEY"] = "habitboost-demo-secret-key"

HABIT_SUGGESTIONS = [
    "Drink 8 Glasses of Water",
    "Morning Walk",
    "Read 20 Pages",
    "Meditate for 10 Minutes",
    "Sleep Before 11 PM",
]

HABIT_CATEGORIES = ["Fitness", "Study", "Health", "Mind", "Work", "Home", "General"]
HABIT_COLORS = [
    ("#f7a9a8", "Pastel Coral"),
    ("#ffd6ba", "Peach"),
    ("#d8c7ff", "Lavender"),
    ("#bfe7c3", "Mint"),
    ("#ffe08a", "Butter"),
]
MOODS = [
    ("happy", "Happy"),
    ("focused", "Focused"),
    ("tired", "Tired"),
    ("stressed", "Stressed"),
]
HABIT_BADGES = [
    {
        "key": "three_day_streak",
        "label": "Getting Started",
        "detail": "Reach a 3 day streak.",
        "icon": "3",
        "requirement": 3,
        "metric": "streak",
    },
    {
        "key": "seven_day_streak",
        "label": "Consistent",
        "detail": "Reach a 7 day streak.",
        "icon": "7",
        "requirement": 7,
        "metric": "streak",
    },
    {
        "key": "fourteen_day_streak",
        "label": "On Fire",
        "detail": "Reach a 14 day streak.",
        "icon": "14",
        "requirement": 14,
        "metric": "streak",
    },
    {
        "key": "thirty_day_streak",
        "label": "Habit Master",
        "detail": "Reach a 30 day streak.",
        "icon": "30",
        "requirement": 30,
        "metric": "streak",
    },
]

CHART_DAYS = 7
HISTORY_DAYS = 35
SAMPLE_PASSWORD_HASH_METHOD = "pbkdf2:sha256:1000000"


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE, timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA busy_timeout = 10000")
        ensure_tracking_schema(g.db)
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    cursor = db.cursor()

    cursor.executescript(
        """
        DROP TABLE IF EXISTS habit_completions;
        DROP TABLE IF EXISTS habits;
        DROP TABLE IF EXISTS users;

        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        );

        CREATE TABLE habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            streak INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'General',
            color TEXT NOT NULL DEFAULT '#f7a9a8',
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE habit_completions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            completed_on TEXT NOT NULL,
            mood TEXT,
            note TEXT,
            FOREIGN KEY (habit_id) REFERENCES habits (id),
            FOREIGN KEY (user_id) REFERENCES users (id),
            UNIQUE (habit_id, completed_on)
        );
        """
    )

    users = [
        ("Alice Johnson", "alice@habitboost.com", "alice123"),
        ("Ben Carter", "ben@habitboost.com", "ben12345"),
        ("Chloe Patel", "chloe@habitboost.com", hash_sample_password("chloe123")),
        ("Daniel Smith", "daniel@habitboost.com", hash_sample_password("daniel123")),
        ("Ella Brooks", "ella@habitboost.com", hash_sample_password("ella1234")),
        ("Farah Khan", "farah@habitboost.com", hash_sample_password("farah123")),
        ("Grace Miller", "grace@habitboost.com", hash_sample_password("grace123")),
        ("Henry Wilson", "henry@habitboost.com", hash_sample_password("henry123")),
    ]
    cursor.executemany("INSERT INTO users (name, email, password) VALUES (?, ?, ?)", users)

    habits = [
        (1, "Morning Workout", 12, "On Track"),
        (1, "Read 20 Pages", 8, "On Track"),
        (1, "Meditate for 10 Minutes", 4, "Needs Focus"),
        (2, "Drink More Water", 15, "Excellent"),
        (2, "Sleep Before 11 PM", 5, "Needs Focus"),
        (2, "Evening Stretch", 9, "On Track"),
        (3, "Journal Before Bed", 18, "Excellent"),
        (3, "Walk 8,000 Steps", 11, "On Track"),
        (3, "No Phone at Breakfast", 6, "Getting Started"),
        (4, "Meal Prep Lunch", 7, "On Track"),
        (4, "Practice Guitar", 21, "Excellent"),
        (5, "Study Spanish", 13, "On Track"),
        (5, "Tidy Desk", 3, "Getting Started"),
        (6, "Cycle to Work", 10, "On Track"),
        (6, "Plan Tomorrow", 16, "Excellent"),
        (7, "Yoga Session", 6, "Needs Focus"),
        (7, "Read Industry News", 14, "On Track"),
        (8, "Budget Check-In", 20, "Excellent"),
        (8, "Cook at Home", 8, "On Track"),
    ]
    cursor.executemany(
        "INSERT INTO habits (user_id, title, streak, status) VALUES (?, ?, ?, ?)", habits
    )
    seed_completion_history(cursor)

    db.commit()
    db.close()


def ensure_tracking_schema(db):
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS habit_completions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            completed_on TEXT NOT NULL,
            mood TEXT,
            note TEXT,
            FOREIGN KEY (habit_id) REFERENCES habits (id),
            FOREIGN KEY (user_id) REFERENCES users (id),
            UNIQUE (habit_id, completed_on)
        )
        """
    )
    ensure_column(db, "habits", "category", "TEXT NOT NULL DEFAULT 'General'")
    ensure_column(db, "habits", "color", "TEXT NOT NULL DEFAULT '#f7a9a8'")
    ensure_column(db, "habit_completions", "mood", "TEXT")
    ensure_column(db, "habit_completions", "note", "TEXT")
    backfill_missing_completion_moods(db)
    db.commit()


def ensure_column(db, table, column, definition):
    columns = db.execute(f"PRAGMA table_info({table})").fetchall()
    if not any(existing["name"] == column for existing in columns):
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def backfill_missing_completion_moods(db):
    rows = db.execute(
        "SELECT id FROM habit_completions WHERE mood IS NULL OR mood = '' ORDER BY id"
    ).fetchall()
    for index, row in enumerate(rows):
        mood = MOODS[(row["id"] + index) % len(MOODS)][0]
        db.execute("UPDATE habit_completions SET mood = ? WHERE id = ?", (mood, row["id"]))


def seed_completion_history(cursor):
    today = date.today()
    habits = cursor.execute(
        "SELECT id, user_id, streak, status FROM habits ORDER BY id"
    ).fetchall()

    for habit_id, user_id, streak, status in habits:
        days_to_seed = min(streak, HISTORY_DAYS)
        for offset in range(days_to_seed):
            if status == "Needs Focus" and offset % 4 == 1:
                continue
            if status == "Getting Started" and offset % 3 != 0:
                continue

            completed_on = today - timedelta(days=offset)
            mood = MOODS[(habit_id + offset) % len(MOODS)][0]
            cursor.execute(
                """
                INSERT OR IGNORE INTO habit_completions
                    (habit_id, user_id, completed_on, mood, note)
                VALUES (?, ?, ?, ?, ?)
                """,
                (habit_id, user_id, completed_on.isoformat(), mood, ""),
            )


def build_progress_chart(db, user_id):
    today = date.today()
    habits_total = db.execute(
        "SELECT COUNT(*) FROM habits WHERE user_id = ?",
        (user_id,),
    ).fetchone()[0]
    target = max(habits_total, 1)
    points = []

    for index in range(CHART_DAYS):
        day = today - timedelta(days=CHART_DAYS - index - 1)
        completed = db.execute(
            """
            SELECT COUNT(*) FROM habit_completions
            WHERE user_id = ? AND completed_on = ?
            """,
            (user_id, day.isoformat()),
        ).fetchone()[0]
        percent = round((completed / target) * 100)
        points.append(
            {
                "label": day.strftime("%a"),
                "date": day.strftime("%d %b"),
                "completed": completed,
                "target": habits_total,
                "percent": percent,
                "x": 8 + (index * (84 / (CHART_DAYS - 1))),
                "y": 90 - (min(percent, 100) * 0.72),
                "color": progress_color(percent),
                "caption": f"{completed}/{habits_total}",
            }
        )

    segments = []
    for index in range(1, len(points)):
        segments.append(
            {
                "start": points[index - 1],
                "end": points[index],
                "color": points[index]["color"],
            }
        )

    return {
        "points": points,
        "segments": segments,
        "line_points": " ".join(f"{point['x']:.2f},{point['y']:.2f}" for point in points),
        "summary": progress_summary(points[-1]["percent"], habits_total),
    }


def build_month_calendar(db, user_id):
    today = date.today()
    month_start = today.replace(day=1)
    _, days_in_month = calendar.monthrange(today.year, today.month)
    month_days = {
        month_start.replace(day=day).isoformat()
        for day in range(1, days_in_month + 1)
    }
    habits_total = db.execute(
        "SELECT COUNT(*) FROM habits WHERE user_id = ?",
        (user_id,),
    ).fetchone()[0]
    target = max(habits_total, 1)
    completions = {
        row["completed_on"]: row["completed"]
        for row in db.execute(
            """
            SELECT completed_on, COUNT(*) AS completed
            FROM habit_completions
            WHERE user_id = ? AND completed_on BETWEEN ? AND ?
            GROUP BY completed_on
            """,
            (
                user_id,
                month_start.isoformat(),
                month_start.replace(day=days_in_month).isoformat(),
            ),
        ).fetchall()
    }
    completed_habits = {}
    for row in db.execute(
        """
        SELECT habit_completions.completed_on, habits.title
        FROM habit_completions
        JOIN habits ON habits.id = habit_completions.habit_id
        WHERE habit_completions.user_id = ?
            AND habit_completions.completed_on BETWEEN ? AND ?
        ORDER BY habit_completions.completed_on, habits.title
        """,
        (
            user_id,
            month_start.isoformat(),
            month_start.replace(day=days_in_month).isoformat(),
        ),
    ).fetchall():
        completed_habits.setdefault(row["completed_on"], []).append(row["title"])

    weeks = []
    for week in calendar.Calendar(firstweekday=0).monthdatescalendar(today.year, today.month):
        week_days = []
        for day in week:
            in_month = day.isoformat() in month_days
            completed = completions.get(day.isoformat(), 0) if in_month else 0
            percent = round((completed / target) * 100) if in_month else 0
            is_future = day > today
            week_days.append(
                {
                    "number": day.day,
                    "iso": day.isoformat(),
                    "date": day.strftime("%d %b"),
                    "completed": completed,
                    "target": habits_total,
                    "tasks": completed_habits.get(day.isoformat(), []),
                    "percent": percent,
                    "in_month": in_month,
                    "is_today": day == today,
                    "is_future": is_future,
                    "color": "future" if is_future else progress_color(percent),
                }
            )
        weeks.append(week_days)

    return {
        "month_label": today.strftime("%B %Y"),
        "weekday_labels": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "weeks": weeks,
    }


def build_dashboard_stats(db, user_id):
    today = date.today().isoformat()
    habit_total = db.execute(
        "SELECT COUNT(*) FROM habits WHERE user_id = ?",
        (user_id,),
    ).fetchone()[0]
    completed_today = db.execute(
        """
        SELECT COUNT(*) FROM habit_completions
        WHERE user_id = ? AND completed_on = ?
        """,
        (user_id, today),
    ).fetchone()[0]
    best_streak = db.execute(
        "SELECT COALESCE(MAX(streak), 0) FROM habits WHERE user_id = ?",
        (user_id,),
    ).fetchone()[0]
    today_percent = round((completed_today / max(habit_total, 1)) * 100)

    return {
        "habit_total": habit_total,
        "completed_today": completed_today,
        "today_percent": today_percent,
        "best_streak": best_streak,
    }


def build_mood_trends(db, user_id):
    start = (date.today() - timedelta(days=HISTORY_DAYS - 1)).isoformat()
    rows = db.execute(
        """
        SELECT mood, COUNT(*) AS total
        FROM habit_completions
        WHERE user_id = ?
            AND completed_on >= ?
            AND mood IS NOT NULL
            AND mood != ''
        GROUP BY mood
        """,
        (user_id, start),
    ).fetchall()
    counts = {row["mood"]: row["total"] for row in rows}
    total = sum(counts.values())
    moods = []

    for value, label in MOODS:
        count = counts.get(value, 0)
        percent = round((count / total) * 100) if total else 0
        moods.append(
            {
                "value": value,
                "label": label,
                "count": count,
                "percent": percent,
            }
        )

    notes = db.execute(
        """
        SELECT habit_completions.completed_on, habit_completions.mood,
            habit_completions.note, habits.title
        FROM habit_completions
        JOIN habits ON habits.id = habit_completions.habit_id
        WHERE habit_completions.user_id = ?
            AND habit_completions.note IS NOT NULL
            AND habit_completions.note != ''
        ORDER BY habit_completions.completed_on DESC, habit_completions.id DESC
        LIMIT 5
        """,
        (user_id,),
    ).fetchall()

    return {
        "moods": moods,
        "total": total,
        "notes": notes,
    }


def get_user_habits(db, user_id):
    rows = db.execute(
        """
        SELECT
            habits.id,
            habits.title,
            habits.streak,
            habits.status,
            habits.category,
            habits.color,
            COUNT(all_completions.id) AS total_completions,
            CASE
                WHEN today_completions.id IS NULL THEN 0
                ELSE 1
            END AS completed_today
        FROM habits
        LEFT JOIN habit_completions AS today_completions
            ON today_completions.habit_id = habits.id
            AND today_completions.completed_on = ?
        LEFT JOIN habit_completions AS all_completions
            ON all_completions.habit_id = habits.id
        WHERE habits.user_id = ?
        GROUP BY habits.id
        ORDER BY habits.id ASC
        """,
        (date.today().isoformat(), user_id),
    ).fetchall()
    reminders = get_user_reminders(user_id)
    return [build_habit_card(row, reminders.get(str(row["id"]))) for row in rows]


def build_habit_card(row, reminder_time=None):
    habit = dict(row)
    habit["reminder_time"] = reminder_time
    habit["badges"] = build_habit_badges(habit)
    habit["earned_badges"] = sum(1 for badge in habit["badges"] if badge["earned"])
    return habit


def build_habit_badges(habit):
    badges = []
    for badge in HABIT_BADGES:
        current = habit[badge["metric"]]
        earned = current >= badge["requirement"]
        badges.append(
            {
                **badge,
                "earned": earned,
                "current": min(current, badge["requirement"]),
            }
        )
    return badges


def progress_color(percent):
    if percent >= 80:
        return "good"
    if percent >= 45:
        return "steady"
    return "behind"


def progress_summary(percent, habits_total):
    if habits_total == 0:
        return "Add your first habit to start tracking today."
    if percent >= 80:
        return "You are on track with your habits today."
    if percent >= 45:
        return "You are building momentum today."
    return "A checkpoint or two will get today moving."


def normalize_reminder_time(value):
    value = (value or "").strip()
    if not value:
        return None

    try:
        hours, minutes = value.split(":", 1)
        hours = int(hours)
        minutes = int(minutes)
    except ValueError:
        return None

    if 0 <= hours <= 23 and 0 <= minutes <= 59:
        return f"{hours:02d}:{minutes:02d}"
    return None


def load_habit_reminders():
    if not os.path.exists(REMINDERS_FILE):
        return {}

    try:
        with open(REMINDERS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}

    if isinstance(data, dict):
        return data
    return {}


def save_habit_reminders(reminders):
    with open(REMINDERS_FILE, "w", encoding="utf-8") as file:
        json.dump(reminders, file, indent=2, sort_keys=True)


def habit_reminder_key(user_id, habit_id):
    return f"{user_id}:{habit_id}"


def get_habit_reminder(user_id, habit_id):
    return load_habit_reminders().get(habit_reminder_key(user_id, habit_id))


def get_user_reminders(user_id):
    prefix = f"{user_id}:"
    reminders = {}
    for key, reminder_time in load_habit_reminders().items():
        if key.startswith(prefix):
            reminders[key.removeprefix(prefix)] = reminder_time
    return reminders


def set_habit_reminder(user_id, habit_id, reminder_time):
    reminders = load_habit_reminders()
    key = habit_reminder_key(user_id, habit_id)

    if reminder_time:
        reminders[key] = reminder_time
    else:
        reminders.pop(key, None)

    save_habit_reminders(reminders)


def delete_habit_reminder(user_id, habit_id):
    reminders = load_habit_reminders()
    reminders.pop(habit_reminder_key(user_id, habit_id), None)
    save_habit_reminders(reminders)


def users_has_role_column(db):
    columns = db.execute("PRAGMA table_info(users)").fetchall()
    return any(column["name"] == "role" for column in columns)


def hash_sample_password(password):
    return generate_password_hash(password, method=SAMPLE_PASSWORD_HASH_METHOD)


def password_matches(stored_password, submitted_password):
    if stored_password.startswith(("scrypt:", "pbkdf2:", "argon2:")):
        return check_password_hash(stored_password, submitted_password)
    return stored_password == submitted_password


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if session.get("user_id") is None:
            flash("Please log in first.", "error")
            return redirect(url_for("index"))

        return view(*args, **kwargs)

    return wrapped_view


@app.route("/", methods=["GET", "POST"])
def index():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        db = get_db()
        if users_has_role_column(db):
            user = db.execute(
                "SELECT * FROM users WHERE email = ? AND role = ?",
                (email, "user"),
            ).fetchone()
        else:
            user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

        if user and password_matches(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            flash(f"Welcome back, {user['name']}!", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid login details. Please try again.", "error")

    return render_template("index.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not name or not email or not password:
            flash("Please fill in every field.", "error")
            return render_template("signup.html")

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("signup.html")

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("signup.html")

        db = get_db()
        existing_user = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing_user:
            flash("An account with that email already exists.", "error")
            return render_template("signup.html")

        password_hash = generate_password_hash(password)
        if users_has_role_column(db):
            cursor = db.execute(
                "INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)",
                (name, email, password_hash, "user"),
            )
        else:
            cursor = db.execute(
                "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
                (name, email, password_hash),
            )
        db.commit()

        session.clear()
        session["user_id"] = cursor.lastrowid
        session["name"] = name
        flash("Your account is ready. Time to build the streak.", "success")
        return redirect(url_for("dashboard"))

    return render_template("signup.html")


@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    return render_template(
        "dashboard.html",
        habits=get_user_habits(db, session["user_id"]),
        moods=MOODS,
        stats=build_dashboard_stats(db, session["user_id"]),
    )


@app.route("/progress")
@login_required
def progress():
    db = get_db()
    return render_template(
        "progress.html",
        progress_chart=build_progress_chart(db, session["user_id"]),
        mood_trends=build_mood_trends(db, session["user_id"]),
        history_days=HISTORY_DAYS,
        stats=build_dashboard_stats(db, session["user_id"]),
    )


@app.route("/calendar")
@login_required
def calendar_view():
    db = get_db()
    return render_template(
        "calendar.html",
        month_calendar=build_month_calendar(db, session["user_id"]),
        stats=build_dashboard_stats(db, session["user_id"]),
    )


@app.route("/habits/new")
@login_required
def new_habit():
    db = get_db()
    return render_template(
        "new_habit.html",
        suggestions=HABIT_SUGGESTIONS,
        categories=HABIT_CATEGORIES,
        colors=HABIT_COLORS,
        stats=build_dashboard_stats(db, session["user_id"]),
    )


@app.route("/habits/<int:habit_id>/edit", methods=["GET", "POST"])
@login_required
def edit_habit(habit_id):
    db = get_db()
    habit = db.execute(
        "SELECT * FROM habits WHERE id = ? AND user_id = ?",
        (habit_id, session["user_id"]),
    ).fetchone()

    if habit is None:
        flash("Habit not found.", "error")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        category = request.form.get("category", "General")
        color = request.form.get("color", "#f7a9a8")
        reminder_time = normalize_reminder_time(request.form.get("reminder_time"))

        if not title:
            flash("Please enter a habit name.", "error")
            return redirect(url_for("edit_habit", habit_id=habit_id))

        if category not in HABIT_CATEGORIES:
            category = "General"

        if color not in {option[0] for option in HABIT_COLORS}:
            color = "#f7a9a8"

        db.execute(
            """
            UPDATE habits
            SET title = ?, category = ?, color = ?
            WHERE id = ? AND user_id = ?
            """,
            (title, category, color, habit_id, session["user_id"]),
        )
        db.commit()
        set_habit_reminder(session["user_id"], habit_id, reminder_time)

        flash(f'"{title}" was updated.', "success")
        return redirect(url_for("dashboard"))

    habit = dict(habit)
    habit["reminder_time"] = get_habit_reminder(session["user_id"], habit_id)

    return render_template(
        "edit_habit.html",
        habit=habit,
        categories=HABIT_CATEGORIES,
        colors=HABIT_COLORS,
    )


@app.route("/habits/<int:habit_id>/reminder", methods=["POST"])
@login_required
def update_habit_reminder(habit_id):
    db = get_db()
    habit = db.execute(
        "SELECT title FROM habits WHERE id = ? AND user_id = ?",
        (habit_id, session["user_id"]),
    ).fetchone()

    if habit is None:
        flash("Habit not found.", "error")
        return redirect(url_for("dashboard"))

    reminder_time = normalize_reminder_time(request.form.get("reminder_time"))
    set_habit_reminder(session["user_id"], habit_id, reminder_time)

    if reminder_time:
        flash(f'Reminder set for "{habit["title"]}" at {reminder_time}.', "success")
    else:
        flash(f'Reminder cleared for "{habit["title"]}".', "success")

    return redirect(url_for("dashboard"))


@app.route("/account", methods=["GET", "POST"])
@login_required
def account():
    db = get_db()
    user = db.execute(
        "SELECT id, name, email FROM users WHERE id = ?",
        (session["user_id"],),
    ).fetchone()

    if user is None:
        session.clear()
        flash("Please log in again.", "error")
        return redirect(url_for("index"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not name or not email:
            flash("Name and email are required.", "error")
            return render_template("account.html", user=user)

        existing_user = db.execute(
            "SELECT id FROM users WHERE email = ? AND id != ?",
            (email, session["user_id"]),
        ).fetchone()
        if existing_user:
            flash("Another account already uses that email.", "error")
            return render_template("account.html", user=user)

        if password or confirm_password:
            if password != confirm_password:
                flash("Passwords do not match.", "error")
                return render_template("account.html", user=user)

            if len(password) < 6:
                flash("Password must be at least 6 characters.", "error")
                return render_template("account.html", user=user)

            db.execute(
                "UPDATE users SET name = ?, email = ?, password = ? WHERE id = ?",
                (name, email, generate_password_hash(password), session["user_id"]),
            )
        else:
            db.execute(
                "UPDATE users SET name = ?, email = ? WHERE id = ?",
                (name, email, session["user_id"]),
            )

        db.commit()
        session["name"] = name
        flash("Account details updated.", "success")
        return redirect(url_for("account"))

    return render_template("account.html", user=user)


@app.route("/delete-account", methods=["POST"])
@login_required
def delete_account():
    db = get_db()
    user_id = session["user_id"]
    db.execute("DELETE FROM habit_completions WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM habits WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()

    session.clear()
    flash("Your account has been deleted.", "success")
    return redirect(url_for("index"))


@app.route("/add-habit", methods=["POST"])
@login_required
def add_habit():
    title = request.form.get("title", "").strip()
    category = request.form.get("category", "General")
    color = request.form.get("color", "#f7a9a8")
    reminder_time = normalize_reminder_time(request.form.get("reminder_time"))

    if not title:
        flash("Please enter a habit name before adding it.", "error")
        return redirect(url_for("new_habit"))

    if category not in HABIT_CATEGORIES:
        category = "General"

    if color not in {option[0] for option in HABIT_COLORS}:
        color = "#f7a9a8"

    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO habits (user_id, title, streak, status, category, color)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (session["user_id"], title, 0, "Getting Started", category, color),
    )
    db.commit()
    set_habit_reminder(session["user_id"], cursor.lastrowid, reminder_time)

    flash(f'"{title}" was added to your habits.', "success")
    return redirect(url_for("dashboard"))


@app.route("/delete-habit/<int:habit_id>", methods=["POST"])
@login_required
def delete_habit(habit_id):
    db = get_db()
    habit = db.execute(
        "SELECT title FROM habits WHERE id = ? AND user_id = ?",
        (habit_id, session["user_id"]),
    ).fetchone()

    if habit is None:
        flash("Habit not found.", "error")
        return redirect(url_for("dashboard"))

    db.execute(
        "DELETE FROM habit_completions WHERE habit_id = ? AND user_id = ?",
        (habit_id, session["user_id"]),
    )
    db.execute(
        "DELETE FROM habits WHERE id = ? AND user_id = ?",
        (habit_id, session["user_id"]),
    )
    db.commit()
    delete_habit_reminder(session["user_id"], habit_id)

    flash(f'"{habit["title"]}" was deleted.', "success")
    return redirect(url_for("dashboard"))


@app.route("/complete-habit/<int:habit_id>", methods=["POST"])
@login_required
def complete_habit(habit_id):
    db = get_db()
    habit = db.execute(
        "SELECT id, title FROM habits WHERE id = ? AND user_id = ?",
        (habit_id, session["user_id"]),
    ).fetchone()

    if habit is None:
        flash("Habit not found.", "error")
        return redirect(url_for("dashboard"))

    today = date.today().isoformat()
    mood = request.form.get("mood", "").strip()
    note = request.form.get("note", "").strip()[:240]

    if mood not in {option[0] for option in MOODS}:
        flash("Please choose how you feel before checking in.", "error")
        return redirect(url_for("dashboard"))

    try:
        db.execute(
            """
            INSERT INTO habit_completions (habit_id, user_id, completed_on, mood, note)
            VALUES (?, ?, ?, ?, ?)
            """,
            (habit_id, session["user_id"], today, mood, note),
        )
    except sqlite3.IntegrityError:
        flash(f'"{habit["title"]}" is already completed for today.', "success")
        return redirect(url_for("dashboard"))

    db.execute(
        """
        UPDATE habits
        SET streak = streak + 1,
            status = ?
        WHERE id = ? AND user_id = ?
        """,
        ("On Track", habit_id, session["user_id"]),
    )
    db.commit()

    flash(f'Today\'s checkpoint is complete for "{habit["title"]}".', "success")
    return redirect(url_for("dashboard"))


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))


if __name__ == "__main__":
    if not os.path.exists(DATABASE):
        init_db()
    app.run(debug=True, use_reloader=False)
