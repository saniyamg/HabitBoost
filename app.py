import os
import sqlite3
from functools import wraps

from flask import Flask, flash, g, redirect, render_template, request, session, url_for


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "database.db")

app = Flask(__name__)
app.config["SECRET_KEY"] = "habitboost-demo-secret-key"

HABIT_SUGGESTIONS = [
    "Drink 8 Glasses of Water",
    "Morning Walk",
    "Read 20 Pages",
    "Meditate for 10 Minutes",
    "Sleep Before 11 PM",
]


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
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
        DROP TABLE IF EXISTS habits;
        DROP TABLE IF EXISTS users;

        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'user'))
        );

        CREATE TABLE habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            streak INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
        """
    )

    users = [
        ("Admin User", "admin@habitboost.com", "admin123", "admin"),
        ("Alice Johnson", "alice@habitboost.com", "user123", "user"),
        ("Ben Carter", "ben@habitboost.com", "user123", "user"),
    ]
    cursor.executemany(
        "INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)", users
    )

    habits = [
        (2, "Morning Workout", 12, "On Track"),
        (2, "Read 20 Pages", 8, "On Track"),
        (3, "Drink More Water", 15, "Excellent"),
        (3, "Sleep Before 11 PM", 5, "Needs Focus"),
    ]
    cursor.executemany(
        "INSERT INTO habits (user_id, title, streak, status) VALUES (?, ?, ?, ?)", habits
    )

    db.commit()
    db.close()


def login_required(role=None):
    def decorator(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            user_id = session.get("user_id")
            user_role = session.get("role")

            if user_id is None:
                flash("Please log in first.", "error")
                return redirect(url_for("index"))

            if role and user_role != role:
                flash("You do not have permission to view that page.", "error")
                return redirect(url_for("dashboard"))

            return view(*args, **kwargs)

        return wrapped_view

    return decorator


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        role = request.form.get("role", "").strip()

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE email = ? AND password = ? AND role = ?",
            (email, password, role),
        ).fetchone()

        if user:
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]
            flash(f"Welcome back, {user['name']}!", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid login details. Please try again.", "error")

    return render_template("index.html")


@app.route("/dashboard")
@login_required()
def dashboard():
    db = get_db()
    role = session["role"]

    if role == "admin":
        users = db.execute(
            """
            SELECT users.id, users.name, users.email, users.role, COUNT(habits.id) AS habit_count
            FROM users
            LEFT JOIN habits ON users.id = habits.user_id
            GROUP BY users.id, users.name, users.email, users.role
            ORDER BY users.role DESC, users.name ASC
            """
        ).fetchall()
        stats = {
            "total_users": len([user for user in users if user["role"] == "user"]),
            "total_admins": len([user for user in users if user["role"] == "admin"]),
            "total_habits": sum(user["habit_count"] for user in users),
        }
        return render_template(
            "dashboard.html",
            users=users,
            stats=stats,
            habits=None,
            suggestions=None,
        )

    habits = db.execute(
        "SELECT title, streak, status FROM habits WHERE user_id = ? ORDER BY id ASC",
        (session["user_id"],),
    ).fetchall()
    return render_template(
        "dashboard.html",
        users=None,
        stats=None,
        habits=habits,
        suggestions=HABIT_SUGGESTIONS,
    )


@app.route("/add-habit", methods=["POST"])
@login_required(role="user")
def add_habit():
    title = request.form.get("title", "").strip()

    if not title:
        flash("Please enter a habit name before adding it.", "error")
        return redirect(url_for("dashboard"))

    db = get_db()
    db.execute(
        "INSERT INTO habits (user_id, title, streak, status) VALUES (?, ?, ?, ?)",
        (session["user_id"], title, 0, "Getting Started"),
    )
    db.commit()

    flash(f'"{title}" was added to your habits.', "success")
    return redirect(url_for("dashboard"))


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))


if __name__ == "__main__":
    if not os.path.exists(DATABASE):
        init_db()
    app.run(debug=True)
