from __future__ import annotations

import functools
import hmac
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = Path(__file__).resolve().parent
DATABASE_SCHEMA = BASE_DIR / "schema.sql"

SKILL_CATEGORIES = (
    "Academic",
    "Arts & Design",
    "Business",
    "Communication",
    "Languages",
    "Lifestyle",
    "Music",
    "Technology",
    "Other",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SWAPSCHOLAR_SECRET_KEY") or secrets.token_hex(32),
        DATABASE=os.environ.get(
            "SWAPSCHOLAR_DATABASE",
            str(Path(app.instance_path) / "swapscholar.sqlite"),
        ),
        SERVER_PUBLIC_IP=os.environ.get("SWAPSCHOLAR_SERVER_IP", "20.46.113.242"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get(
            "SWAPSCHOLAR_COOKIE_SECURE", "0"
        ).lower()
        in {"1", "true", "yes"},
        MAX_CONTENT_LENGTH=1 * 1024 * 1024,
    )

    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)

    app.teardown_appcontext(close_db)
    app.cli.command("init-db")(init_db_command)
    app.cli.command("seed-demo")(seed_demo_command)

    @app.context_processor
    def inject_globals() -> dict:
        return {
            "csrf_token": get_csrf_token,
            "skill_categories": SKILL_CATEGORIES,
            "server_public_ip": app.config["SERVER_PUBLIC_IP"],
        }

    @app.template_filter("friendly_date")
    def friendly_date(value: str | None) -> str:
        if not value:
            return ""
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            return parsed.strftime("%d %b %Y")
        except (TypeError, ValueError):
            return value

    @app.template_filter("initials")
    def initials(value: str | None) -> str:
        words = [word for word in (value or "").split() if word]
        if not words:
            return "SS"
        return "".join(word[0] for word in words[:2]).upper()

    @app.before_request
    def load_user_and_validate_csrf() -> None:
        user_id = session.get("user_id")
        g.user = (
            get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if user_id
            else None
        )

        if request.method == "POST":
            supplied = request.form.get("_csrf_token", "")
            expected = session.get("_csrf_token", "")
            if not supplied or not expected or not hmac.compare_digest(supplied, expected):
                abort(400, description="The form expired. Please go back and try again.")

    with app.app_context():
        ensure_database()

    register_routes(app)
    register_error_handlers(app)
    return app


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(
            _database_from_context(),
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA busy_timeout = 5000")
    return g.db


def _database_from_context() -> str:
    from flask import current_app

    return current_app.config["DATABASE"]


def close_db(_exception: BaseException | None = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def ensure_database() -> None:
    # The schema only uses CREATE ... IF NOT EXISTS, so running it at startup
    # safely creates new tables when an existing deployment is upgraded.
    init_db()


def init_db() -> None:
    db = get_db()
    db.executescript(DATABASE_SCHEMA.read_text(encoding="utf-8"))
    db.commit()


def init_db_command() -> None:
    init_db()
    print("SwapScholar database initialised.")


def seed_demo_command() -> None:
    seed_demo_data()
    print("Demo accounts and sample exchanges added.")


def get_csrf_token() -> str:
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            flash("Please log in to continue.", "info")
            return redirect(url_for("login", next=request.full_path.rstrip("?")))
        return view(**kwargs)

    return wrapped_view


def clean_text(value: str | None, max_length: int) -> str:
    return " ".join((value or "").strip().split())[:max_length]


def clean_multiline(value: str | None, max_length: int) -> str:
    lines = [" ".join(line.strip().split()) for line in (value or "").splitlines()]
    return "\n".join(line for line in lines if line)[:max_length]


def is_safe_next_url(target: str | None) -> bool:
    if not target:
        return False
    parsed = urlsplit(target)
    return not parsed.scheme and not parsed.netloc and target.startswith("/")


def register_routes(app: Flask) -> None:
    @app.get("/")
    def home():
        db = get_db()
        stats = {
            "students": db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            "skills": db.execute(
                "SELECT COUNT(*) FROM skills WHERE direction = 'offer'"
            ).fetchone()[0],
            "categories": db.execute(
                "SELECT COUNT(DISTINCT category) FROM skills WHERE direction = 'offer'"
            ).fetchone()[0],
            "completed": db.execute(
                "SELECT COUNT(*) FROM exchanges WHERE status = 'completed'"
            ).fetchone()[0],
            "reviews": db.execute("SELECT COUNT(*) FROM reviews").fetchone()[0],
            "active": db.execute(
                "SELECT COUNT(*) FROM exchanges WHERE status IN ('pending', 'accepted')"
            ).fetchone()[0],
        }
        featured = db.execute(
            """
            SELECT s.*, u.name AS user_name, u.university,
                   COALESCE(AVG(r.rating), 0) AS rating,
                   COUNT(DISTINCT r.id) AS review_count
            FROM skills s
            JOIN users u ON u.id = s.user_id
            LEFT JOIN reviews r ON r.reviewee_id = u.id
            WHERE s.direction = 'offer'
            GROUP BY s.id
            ORDER BY review_count DESC, s.created_at DESC
            LIMIT 4
            """
        ).fetchall()
        return render_template("home.html", stats=stats, featured=featured)

    @app.route("/register", methods=("GET", "POST"))
    def register():
        if g.user:
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            name = clean_text(request.form.get("name"), 80)
            email = clean_text(request.form.get("email"), 160).lower()
            university = clean_text(request.form.get("university"), 120)
            password = request.form.get("password", "")
            confirm = request.form.get("confirm_password", "")
            error = None

            if len(name) < 2:
                error = "Enter your full name."
            elif "@" not in email or "." not in email.rsplit("@", 1)[-1]:
                error = "Enter a valid email address."
            elif len(university) < 2:
                error = "Enter your university or learning community."
            elif len(password) < 8:
                error = "Password must contain at least 8 characters."
            elif password != confirm:
                error = "The passwords do not match."

            if error is None:
                try:
                    cursor = get_db().execute(
                        """
                        INSERT INTO users
                            (name, email, password_hash, university, credits, created_at)
                        VALUES (?, ?, ?, ?, 2, ?)
                        """,
                        (
                            name,
                            email,
                            generate_password_hash(password),
                            university,
                            utc_now(),
                        ),
                    )
                    get_db().commit()
                    session.clear()
                    session["user_id"] = cursor.lastrowid
                    flash(
                        "Welcome to SwapScholar. Add what you can teach and want to learn.",
                        "success",
                    )
                    return redirect(url_for("manage_skills"))
                except sqlite3.IntegrityError:
                    error = "An account with that email already exists."

            flash(error, "error")

        return render_template("register.html")

    @app.route("/login", methods=("GET", "POST"))
    def login():
        if g.user:
            return redirect(url_for("dashboard"))

        next_url = request.args.get("next", "")
        if request.method == "POST":
            email = clean_text(request.form.get("email"), 160).lower()
            password = request.form.get("password", "")
            next_url = request.form.get("next", "")
            user = get_db().execute(
                "SELECT * FROM users WHERE email = ?", (email,)
            ).fetchone()

            if user is None or not check_password_hash(user["password_hash"], password):
                flash("Incorrect email or password.", "error")
            else:
                session.clear()
                session["user_id"] = user["id"]
                flash(f"Welcome back, {user['name'].split()[0]}.", "success")
                if is_safe_next_url(next_url):
                    return redirect(next_url)
                return redirect(url_for("dashboard"))

        return render_template("login.html", next_url=next_url)

    @app.post("/logout")
    def logout():
        session.clear()
        flash("You have been logged out.", "info")
        return redirect(url_for("home"))

    @app.get("/browse")
    def browse():
        q = clean_text(request.args.get("q"), 100)
        category = clean_text(request.args.get("category"), 40)
        if category not in SKILL_CATEGORIES:
            category = ""
        term = f"%{q}%"

        offers = get_db().execute(
            """
            SELECT s.*, u.name AS user_name, u.university, u.bio,
                   COALESCE(AVG(r.rating), 0) AS rating,
                   COUNT(DISTINCT r.id) AS review_count
            FROM skills s
            JOIN users u ON u.id = s.user_id
            LEFT JOIN reviews r ON r.reviewee_id = u.id
            WHERE s.direction = 'offer'
              AND (
                  ? = ''
                  OR s.name LIKE ?
                  OR s.description LIKE ?
                  OR u.name LIKE ?
                  OR u.university LIKE ?
                  OR s.category LIKE ?
              )
              AND (? = '' OR s.category = ?)
            GROUP BY s.id
            ORDER BY rating DESC, s.created_at DESC
            """,
            (q, term, term, term, term, term, category, category),
        ).fetchall()
        return render_template(
            "browse.html", offers=offers, q=q, selected_category=category
        )

    @app.get("/student/<int:user_id>")
    def profile(user_id: int):
        db = get_db()
        user = db.execute(
            """
            SELECT u.*, COALESCE(AVG(r.rating), 0) AS rating,
                   COUNT(DISTINCT r.id) AS review_count
            FROM users u
            LEFT JOIN reviews r ON r.reviewee_id = u.id
            WHERE u.id = ?
            GROUP BY u.id
            """,
            (user_id,),
        ).fetchone()
        if user is None:
            abort(404)

        offers = db.execute(
            "SELECT * FROM skills WHERE user_id = ? AND direction = 'offer' "
            "ORDER BY name",
            (user_id,),
        ).fetchall()
        wants = db.execute(
            "SELECT * FROM skills WHERE user_id = ? AND direction = 'want' "
            "ORDER BY name",
            (user_id,),
        ).fetchall()
        reviews = db.execute(
            """
            SELECT r.*, reviewer.name AS reviewer_name
            FROM reviews r
            JOIN users reviewer ON reviewer.id = r.reviewer_id
            WHERE r.reviewee_id = ?
            ORDER BY r.created_at DESC
            """,
            (user_id,),
        ).fetchall()
        return render_template(
            "profile.html",
            profile_user=user,
            offers=offers,
            wants=wants,
            reviews=reviews,
        )

    @app.route("/profile/edit", methods=("GET", "POST"))
    @login_required
    def edit_profile():
        if request.method == "POST":
            name = clean_text(request.form.get("name"), 80)
            university = clean_text(request.form.get("university"), 120)
            course = clean_text(request.form.get("course"), 120)
            availability = clean_text(request.form.get("availability"), 160)
            bio = clean_multiline(request.form.get("bio"), 500)

            if len(name) < 2 or len(university) < 2:
                flash("Name and university are required.", "error")
            else:
                get_db().execute(
                    """
                    UPDATE users
                    SET name = ?, university = ?, course = ?, availability = ?, bio = ?
                    WHERE id = ?
                    """,
                    (name, university, course, availability, bio, g.user["id"]),
                )
                get_db().commit()
                flash("Your profile has been updated.", "success")
                return redirect(url_for("profile", user_id=g.user["id"]))

        return render_template("edit_profile.html")

    @app.route("/skills", methods=("GET", "POST"))
    @login_required
    def manage_skills():
        db = get_db()
        if request.method == "POST":
            name = clean_text(request.form.get("name"), 80)
            category = clean_text(request.form.get("category"), 40)
            direction = request.form.get("direction", "")
            level = clean_text(request.form.get("level"), 40)
            description = clean_multiline(request.form.get("description"), 320)

            if len(name) < 2:
                flash("Enter a skill name.", "error")
            elif category not in SKILL_CATEGORIES:
                flash("Choose a valid category.", "error")
            elif direction not in {"offer", "want"}:
                flash("Choose whether you offer or want this skill.", "error")
            else:
                try:
                    db.execute(
                        """
                        INSERT INTO skills
                            (user_id, name, category, direction, level, description, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            g.user["id"],
                            name,
                            category,
                            direction,
                            level,
                            description,
                            utc_now(),
                        ),
                    )
                    db.commit()
                    flash(f"{name} was added to your profile.", "success")
                    return redirect(url_for("manage_skills"))
                except sqlite3.IntegrityError:
                    flash("That skill is already in this list.", "error")

        offers = db.execute(
            "SELECT * FROM skills WHERE user_id = ? AND direction = 'offer' "
            "ORDER BY name",
            (g.user["id"],),
        ).fetchall()
        wants = db.execute(
            "SELECT * FROM skills WHERE user_id = ? AND direction = 'want' "
            "ORDER BY name",
            (g.user["id"],),
        ).fetchall()
        return render_template("skills.html", offers=offers, wants=wants)

    @app.post("/skills/<int:skill_id>/delete")
    @login_required
    def delete_skill(skill_id: int):
        skill = get_db().execute(
            "SELECT * FROM skills WHERE id = ? AND user_id = ?",
            (skill_id, g.user["id"]),
        ).fetchone()
        if skill is None:
            abort(404)
        try:
            get_db().execute("DELETE FROM skills WHERE id = ?", (skill_id,))
            get_db().commit()
            flash(f"{skill['name']} was removed.", "info")
        except sqlite3.IntegrityError:
            flash(
                "This skill is linked to an exchange and cannot be removed yet.",
                "error",
            )
        return redirect(url_for("manage_skills"))

    @app.get("/matches")
    @login_required
    def matches():
        db = get_db()
        my_skills = db.execute(
            "SELECT * FROM skills WHERE user_id = ?", (g.user["id"],)
        ).fetchall()
        my_offers = {
            skill["name"].casefold(): skill for skill in my_skills if skill["direction"] == "offer"
        }
        my_wants = {
            skill["name"].casefold(): skill for skill in my_skills if skill["direction"] == "want"
        }

        other_users = db.execute(
            """
            SELECT u.*, COALESCE(AVG(r.rating), 0) AS rating,
                   COUNT(DISTINCT r.id) AS review_count
            FROM users u
            LEFT JOIN reviews r ON r.reviewee_id = u.id
            WHERE u.id != ?
            GROUP BY u.id
            """,
            (g.user["id"],),
        ).fetchall()
        all_other_skills = db.execute(
            "SELECT * FROM skills WHERE user_id != ?", (g.user["id"],)
        ).fetchall()

        skills_by_user: dict[int, list[sqlite3.Row]] = {}
        for skill in all_other_skills:
            skills_by_user.setdefault(skill["user_id"], []).append(skill)

        results = []
        for user in other_users:
            their_skills = skills_by_user.get(user["id"], [])
            their_offers = {
                skill["name"].casefold(): skill
                for skill in their_skills
                if skill["direction"] == "offer"
            }
            their_wants = {
                skill["name"].casefold(): skill
                for skill in their_skills
                if skill["direction"] == "want"
            }
            they_teach = [their_offers[name] for name in my_wants.keys() & their_offers.keys()]
            they_learn = [their_wants[name] for name in my_offers.keys() & their_wants.keys()]
            if they_teach:
                results.append(
                    {
                        "user": user,
                        "they_teach": they_teach,
                        "they_learn": they_learn,
                        "mutual": bool(they_teach and they_learn),
                        "score": len(they_teach) * 2 + len(they_learn),
                    }
                )

        results.sort(key=lambda item: (item["mutual"], item["score"]), reverse=True)
        return render_template(
            "matches.html",
            matches=results,
            has_offers=bool(my_offers),
            has_wants=bool(my_wants),
        )

    @app.route("/request/<int:skill_id>", methods=("GET", "POST"))
    @login_required
    def request_exchange(skill_id: int):
        db = get_db()
        requested_skill = db.execute(
            """
            SELECT s.*, u.name AS owner_name, u.university, u.id AS owner_id
            FROM skills s
            JOIN users u ON u.id = s.user_id
            WHERE s.id = ? AND s.direction = 'offer'
            """,
            (skill_id,),
        ).fetchone()
        if requested_skill is None:
            abort(404)
        if requested_skill["owner_id"] == g.user["id"]:
            flash("You cannot request your own skill.", "error")
            return redirect(url_for("manage_skills"))

        my_offers = db.execute(
            "SELECT * FROM skills WHERE user_id = ? AND direction = 'offer' ORDER BY name",
            (g.user["id"],),
        ).fetchall()
        recipient_wants = {
            row["name"].casefold()
            for row in db.execute(
                "SELECT name FROM skills WHERE user_id = ? AND direction = 'want'",
                (requested_skill["owner_id"],),
            ).fetchall()
        }

        if request.method == "POST":
            mode = request.form.get("mode", "")
            offered_skill_id = request.form.get("offered_skill_id", type=int)
            message = clean_multiline(request.form.get("message"), 500)
            preferred_schedule = clean_text(
                request.form.get("preferred_schedule"), 160
            )
            error = None

            if mode not in {"swap", "credit"}:
                error = "Choose mutual swap or one time credit."
            elif mode == "credit" and g.user["credits"] < 1:
                error = "You need at least one time credit for this request."
            elif mode == "swap":
                offered = db.execute(
                    """
                    SELECT * FROM skills
                    WHERE id = ? AND user_id = ? AND direction = 'offer'
                    """,
                    (offered_skill_id, g.user["id"]),
                ).fetchone()
                if offered is None:
                    error = "Choose one of your offered skills for the swap."

            duplicate = db.execute(
                """
                SELECT id FROM exchanges
                WHERE requester_id = ? AND recipient_id = ?
                  AND requested_skill_id = ?
                  AND status IN ('pending', 'accepted')
                """,
                (g.user["id"], requested_skill["owner_id"], skill_id),
            ).fetchone()
            if duplicate:
                error = "You already have an active request for this skill."

            if error:
                flash(error, "error")
            else:
                db.execute(
                    """
                    INSERT INTO exchanges
                        (requester_id, recipient_id, requested_skill_id,
                         offered_skill_id, mode, message, preferred_schedule,
                         status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                    """,
                    (
                        g.user["id"],
                        requested_skill["owner_id"],
                        skill_id,
                        offered_skill_id if mode == "swap" else None,
                        mode,
                        message,
                        preferred_schedule,
                        utc_now(),
                        utc_now(),
                    ),
                )
                db.commit()
                flash("Your exchange request has been sent.", "success")
                return redirect(url_for("dashboard"))

        return render_template(
            "request_exchange.html",
            requested_skill=requested_skill,
            my_offers=my_offers,
            recipient_wants=recipient_wants,
        )

    @app.get("/dashboard")
    @login_required
    def dashboard():
        db = get_db()
        exchange_select = """
            SELECT e.*,
                   requester.name AS requester_name,
                   recipient.name AS recipient_name,
                   requested.name AS requested_skill_name,
                   offered.name AS offered_skill_name,
                   EXISTS(
                       SELECT 1 FROM reviews r
                       WHERE r.exchange_id = e.id AND r.reviewer_id = ?
                   ) AS reviewed_by_me
            FROM exchanges e
            JOIN users requester ON requester.id = e.requester_id
            JOIN users recipient ON recipient.id = e.recipient_id
            JOIN skills requested ON requested.id = e.requested_skill_id
            LEFT JOIN skills offered ON offered.id = e.offered_skill_id
        """
        incoming = db.execute(
            exchange_select
            + " WHERE e.recipient_id = ? ORDER BY e.created_at DESC",
            (g.user["id"], g.user["id"]),
        ).fetchall()
        outgoing = db.execute(
            exchange_select
            + " WHERE e.requester_id = ? ORDER BY e.created_at DESC",
            (g.user["id"], g.user["id"]),
        ).fetchall()
        counts = {
            "pending": db.execute(
                """
                SELECT COUNT(*) FROM exchanges
                WHERE recipient_id = ? AND status = 'pending'
                """,
                (g.user["id"],),
            ).fetchone()[0],
            "matches": len(_quick_match_ids(db, g.user["id"])),
            "completed": db.execute(
                """
                SELECT COUNT(*) FROM exchanges
                WHERE (requester_id = ? OR recipient_id = ?) AND status = 'completed'
                """,
                (g.user["id"], g.user["id"]),
            ).fetchone()[0],
        }
        return render_template(
            "dashboard.html", incoming=incoming, outgoing=outgoing, counts=counts
        )

    @app.post("/exchange/<int:exchange_id>/action")
    @login_required
    def exchange_action(exchange_id: int):
        db = get_db()
        exchange = db.execute(
            "SELECT * FROM exchanges WHERE id = ?", (exchange_id,)
        ).fetchone()
        if exchange is None:
            abort(404)
        if g.user["id"] not in {exchange["requester_id"], exchange["recipient_id"]}:
            abort(403)

        action = request.form.get("action", "")
        now = utc_now()
        try:
            db.execute("BEGIN IMMEDIATE")
            exchange = db.execute(
                "SELECT * FROM exchanges WHERE id = ?", (exchange_id,)
            ).fetchone()

            if action == "accept":
                if (
                    g.user["id"] != exchange["recipient_id"]
                    or exchange["status"] != "pending"
                ):
                    abort(403)
                if exchange["mode"] == "credit":
                    requester = db.execute(
                        "SELECT credits FROM users WHERE id = ?",
                        (exchange["requester_id"],),
                    ).fetchone()
                    if requester["credits"] < 1:
                        db.rollback()
                        flash(
                            "The requester no longer has a credit. Ask them to earn one first.",
                            "error",
                        )
                        return redirect(url_for("dashboard"))
                    db.execute(
                        "UPDATE users SET credits = credits - 1 WHERE id = ?",
                        (exchange["requester_id"],),
                    )
                    db.execute(
                        """
                        UPDATE exchanges
                        SET status = 'accepted', credit_reserved = 1, updated_at = ?
                        WHERE id = ?
                        """,
                        (now, exchange_id),
                    )
                else:
                    db.execute(
                        "UPDATE exchanges SET status = 'accepted', updated_at = ? "
                        "WHERE id = ?",
                        (now, exchange_id),
                    )
                flash("Exchange accepted. Arrange the session and confirm it afterwards.", "success")

            elif action == "reject":
                if (
                    g.user["id"] != exchange["recipient_id"]
                    or exchange["status"] != "pending"
                ):
                    abort(403)
                db.execute(
                    "UPDATE exchanges SET status = 'rejected', updated_at = ? WHERE id = ?",
                    (now, exchange_id),
                )
                flash("Exchange request declined.", "info")

            elif action == "cancel":
                if (
                    g.user["id"] != exchange["requester_id"]
                    or exchange["status"] != "pending"
                ):
                    abort(403)
                db.execute(
                    "UPDATE exchanges SET status = 'cancelled', updated_at = ? WHERE id = ?",
                    (now, exchange_id),
                )
                flash("Exchange request cancelled.", "info")

            elif action == "complete":
                if exchange["status"] != "accepted":
                    abort(403)
                if g.user["id"] == exchange["requester_id"]:
                    db.execute(
                        """
                        UPDATE exchanges
                        SET requester_complete = 1, updated_at = ?
                        WHERE id = ?
                        """,
                        (now, exchange_id),
                    )
                else:
                    db.execute(
                        """
                        UPDATE exchanges
                        SET recipient_complete = 1, updated_at = ?
                        WHERE id = ?
                        """,
                        (now, exchange_id),
                    )
                updated = db.execute(
                    "SELECT * FROM exchanges WHERE id = ?", (exchange_id,)
                ).fetchone()
                if updated["requester_complete"] and updated["recipient_complete"]:
                    db.execute(
                        """
                        UPDATE exchanges
                        SET status = 'completed', completed_at = ?, updated_at = ?
                        WHERE id = ? AND status = 'accepted'
                        """,
                        (now, now, exchange_id),
                    )
                    if updated["mode"] == "credit" and updated["credit_reserved"]:
                        db.execute(
                            "UPDATE users SET credits = credits + 1 WHERE id = ?",
                            (updated["recipient_id"],),
                        )
                    flash("Exchange completed. You can now leave a review.", "success")
                else:
                    flash("Completion recorded. Waiting for the other student.", "success")
            else:
                abort(400)

            db.commit()
        except sqlite3.Error:
            db.rollback()
            raise
        return redirect(url_for("dashboard"))

    @app.route("/exchange/<int:exchange_id>/messages", methods=("GET", "POST"))
    @login_required
    def exchange_messages(exchange_id: int):
        db = get_db()
        exchange = db.execute(
            """
            SELECT e.*, requester.name AS requester_name,
                   recipient.name AS recipient_name,
                   requested.name AS requested_skill_name,
                   offered.name AS offered_skill_name
            FROM exchanges e
            JOIN users requester ON requester.id = e.requester_id
            JOIN users recipient ON recipient.id = e.recipient_id
            JOIN skills requested ON requested.id = e.requested_skill_id
            LEFT JOIN skills offered ON offered.id = e.offered_skill_id
            WHERE e.id = ?
            """,
            (exchange_id,),
        ).fetchone()
        if exchange is None:
            abort(404)
        if g.user["id"] not in {exchange["requester_id"], exchange["recipient_id"]}:
            abort(403)
        if exchange["status"] not in {"accepted", "completed"}:
            abort(403)

        other_name = (
            exchange["recipient_name"]
            if g.user["id"] == exchange["requester_id"]
            else exchange["requester_name"]
        )

        if request.method == "POST":
            body = clean_multiline(request.form.get("body"), 1000)
            if not body:
                flash("Write a message before sending.", "error")
            else:
                db.execute(
                    """
                    INSERT INTO exchange_messages
                        (exchange_id, sender_id, body, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (exchange_id, g.user["id"], body, utc_now()),
                )
                db.commit()
                flash(f"Message sent to {other_name}.", "success")
                return redirect(
                    url_for("exchange_messages", exchange_id=exchange_id)
                    + "#latest-message"
                )

        messages = db.execute(
            """
            SELECT m.*, u.name AS sender_name
            FROM exchange_messages m
            JOIN users u ON u.id = m.sender_id
            WHERE m.exchange_id = ?
            ORDER BY m.created_at, m.id
            """,
            (exchange_id,),
        ).fetchall()
        return render_template(
            "messages.html",
            exchange=exchange,
            messages=messages,
            other_name=other_name,
        )

    @app.route("/exchange/<int:exchange_id>/review", methods=("GET", "POST"))
    @login_required
    def review_exchange(exchange_id: int):
        db = get_db()
        exchange = db.execute(
            """
            SELECT e.*, requester.name AS requester_name,
                   recipient.name AS recipient_name,
                   requested.name AS requested_skill_name
            FROM exchanges e
            JOIN users requester ON requester.id = e.requester_id
            JOIN users recipient ON recipient.id = e.recipient_id
            JOIN skills requested ON requested.id = e.requested_skill_id
            WHERE e.id = ?
            """,
            (exchange_id,),
        ).fetchone()
        if exchange is None:
            abort(404)
        if g.user["id"] not in {exchange["requester_id"], exchange["recipient_id"]}:
            abort(403)
        if exchange["status"] != "completed":
            flash("Reviews are available after both students complete the exchange.", "info")
            return redirect(url_for("dashboard"))

        existing = db.execute(
            "SELECT id FROM reviews WHERE exchange_id = ? AND reviewer_id = ?",
            (exchange_id, g.user["id"]),
        ).fetchone()
        if existing:
            flash("You have already reviewed this exchange.", "info")
            return redirect(url_for("dashboard"))

        reviewee_id = (
            exchange["recipient_id"]
            if g.user["id"] == exchange["requester_id"]
            else exchange["requester_id"]
        )
        reviewee_name = (
            exchange["recipient_name"]
            if g.user["id"] == exchange["requester_id"]
            else exchange["requester_name"]
        )

        if request.method == "POST":
            rating = request.form.get("rating", type=int)
            comment = clean_multiline(request.form.get("comment"), 500)
            if rating not in {1, 2, 3, 4, 5}:
                flash("Choose a rating from 1 to 5.", "error")
            elif len(comment) < 5:
                flash("Write a short review of at least 5 characters.", "error")
            else:
                db.execute(
                    """
                    INSERT INTO reviews
                        (exchange_id, reviewer_id, reviewee_id, rating, comment, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        exchange_id,
                        g.user["id"],
                        reviewee_id,
                        rating,
                        comment,
                        utc_now(),
                    ),
                )
                db.commit()
                flash(f"Your review for {reviewee_name} has been published.", "success")
                return redirect(url_for("dashboard"))

        return render_template(
            "review.html", exchange=exchange, reviewee_name=reviewee_name
        )

    @app.get("/statistics")
    def statistics():
        db = get_db()
        stats = {
            "students": db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            "offered": db.execute(
                "SELECT COUNT(*) FROM skills WHERE direction = 'offer'"
            ).fetchone()[0],
            "active": db.execute(
                "SELECT COUNT(*) FROM exchanges WHERE status IN ('pending', 'accepted')"
            ).fetchone()[0],
            "completed": db.execute(
                "SELECT COUNT(*) FROM exchanges WHERE status = 'completed'"
            ).fetchone()[0],
            "reviews": db.execute("SELECT COUNT(*) FROM reviews").fetchone()[0],
        }
        categories = db.execute(
            """
            SELECT category, COUNT(*) AS total
            FROM skills
            WHERE direction = 'offer'
            GROUP BY category
            ORDER BY total DESC, category
            LIMIT 6
            """
        ).fetchall()
        top_members = db.execute(
            """
            SELECT u.id, u.name, u.university, u.credits,
                   COALESCE(AVG(r.rating), 0) AS rating,
                   COUNT(DISTINCT r.id) AS review_count,
                   COUNT(DISTINCT CASE WHEN e.status = 'completed' THEN e.id END)
                       AS completed_count
            FROM users u
            LEFT JOIN reviews r ON r.reviewee_id = u.id
            LEFT JOIN exchanges e
                ON e.requester_id = u.id OR e.recipient_id = u.id
            GROUP BY u.id
            ORDER BY rating DESC, completed_count DESC
            LIMIT 5
            """
        ).fetchall()
        max_category = max((row["total"] for row in categories), default=1)
        return render_template(
            "statistics.html",
            stats=stats,
            categories=categories,
            max_category=max_category,
            top_members=top_members,
        )

    @app.get("/how-it-works")
    def how_it_works():
        return render_template("how_it_works.html")


def _quick_match_ids(db: sqlite3.Connection, user_id: int) -> set[int]:
    my_wants = {
        row["name"].casefold()
        for row in db.execute(
            "SELECT name FROM skills WHERE user_id = ? AND direction = 'want'",
            (user_id,),
        ).fetchall()
    }
    if not my_wants:
        return set()
    return {
        row["user_id"]
        for row in db.execute(
            "SELECT user_id, name FROM skills WHERE user_id != ? AND direction = 'offer'",
            (user_id,),
        ).fetchall()
        if row["name"].casefold() in my_wants
    }


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(400)
    def bad_request(error):
        return (
            render_template(
                "error.html",
                code=400,
                title="That request could not be completed",
                message=getattr(error, "description", "Please check the form and try again."),
            ),
            400,
        )

    @app.errorhandler(403)
    def forbidden(_error):
        return (
            render_template(
                "error.html",
                code=403,
                title="Access not allowed",
                message="You do not have permission to perform that action.",
            ),
            403,
        )

    @app.errorhandler(404)
    def not_found(_error):
        return (
            render_template(
                "error.html",
                code=404,
                title="Page not found",
                message="The page or record you requested does not exist.",
            ),
            404,
        )

    @app.errorhandler(413)
    def too_large(_error):
        return (
            render_template(
                "error.html",
                code=413,
                title="Request too large",
                message="The submitted form is larger than the permitted limit.",
            ),
            413,
        )


def seed_demo_data() -> None:
    db = get_db()
    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
        return

    demo_password = generate_password_hash("Demo123!")
    users = [
        (
            "Aisha Rahman",
            "aisha@demo.swapscholar",
            demo_password,
            "Murdoch University",
            "Information Technology",
            "I enjoy making technical topics easier for beginners.",
            "Weekdays after 4pm",
            3,
        ),
        (
            "Daniel Kim",
            "daniel@demo.swapscholar",
            demo_password,
            "Murdoch University",
            "Digital Media",
            "Designer, photographer and patient peer mentor.",
            "Tuesday and Thursday afternoons",
            2,
        ),
        (
            "Mia Chen",
            "mia@demo.swapscholar",
            demo_password,
            "University Community",
            "Business Analytics",
            "I like practical projects, languages and data visualisation.",
            "Weekends",
            4,
        ),
        (
            "Omar Hassan",
            "omar@demo.swapscholar",
            demo_password,
            "University Community",
            "Commerce",
            "Public-speaking coach learning more about technology.",
            "Monday evenings",
            2,
        ),
    ]
    user_ids: dict[str, int] = {}
    for user in users:
        cursor = db.execute(
            """
            INSERT INTO users
                (name, email, password_hash, university, course, bio,
                 availability, credits, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (*user, utc_now()),
        )
        user_ids[user[0]] = cursor.lastrowid

    skills = [
        ("Aisha Rahman", "Python programming", "Technology", "offer", "Intermediate", "Python basics, functions and small Flask projects."),
        ("Aisha Rahman", "Excel", "Business", "offer", "Advanced", "Formulas, pivot tables and clear dashboards."),
        ("Aisha Rahman", "Photoshop", "Arts & Design", "want", "Beginner", "I want to improve image editing for project work."),
        ("Daniel Kim", "Photoshop", "Arts & Design", "offer", "Advanced", "Photo correction, layers and poster design."),
        ("Daniel Kim", "Photography", "Arts & Design", "offer", "Intermediate", "Camera basics, composition and editing."),
        ("Daniel Kim", "Python programming", "Technology", "want", "Beginner", "I want to automate repetitive design tasks."),
        ("Mia Chen", "Data visualisation", "Technology", "offer", "Intermediate", "Charts, dashboards and presenting data clearly."),
        ("Mia Chen", "Mandarin conversation", "Languages", "offer", "Advanced", "Friendly conversation practice for beginners."),
        ("Mia Chen", "Public speaking", "Communication", "want", "Beginner", "Help with confident class presentations."),
        ("Omar Hassan", "Public speaking", "Communication", "offer", "Advanced", "Presentation structure, confidence and delivery."),
        ("Omar Hassan", "Python programming", "Technology", "want", "Beginner", "Starting from the fundamentals."),
    ]
    skill_ids: dict[tuple[str, str, str], int] = {}
    for owner, name, category, direction, level, description in skills:
        cursor = db.execute(
            """
            INSERT INTO skills
                (user_id, name, category, direction, level, description, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_ids[owner],
                name,
                category,
                direction,
                level,
                description,
                utc_now(),
            ),
        )
        skill_ids[(owner, name, direction)] = cursor.lastrowid

    completed = db.execute(
        """
        INSERT INTO exchanges
            (requester_id, recipient_id, requested_skill_id, offered_skill_id,
             mode, message, preferred_schedule, status, requester_complete,
             recipient_complete, completed_at, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'swap', ?, ?, 'completed', 1, 1, ?, ?, ?)
        """,
        (
            user_ids["Aisha Rahman"],
            user_ids["Daniel Kim"],
            skill_ids[("Daniel Kim", "Photoshop", "offer")],
            skill_ids[("Aisha Rahman", "Python programming", "offer")],
            "Would you like to swap a Photoshop session for Python basics?",
            "Thursday afternoon",
            utc_now(),
            utc_now(),
            utc_now(),
        ),
    ).lastrowid
    db.execute(
        """
        INSERT INTO reviews
            (exchange_id, reviewer_id, reviewee_id, rating, comment, created_at)
        VALUES (?, ?, ?, 5, ?, ?)
        """,
        (
            completed,
            user_ids["Aisha Rahman"],
            user_ids["Daniel Kim"],
            "Clear explanations and a very useful hands-on session.",
            utc_now(),
        ),
    )
    db.execute(
        """
        INSERT INTO exchanges
            (requester_id, recipient_id, requested_skill_id, offered_skill_id,
             mode, message, preferred_schedule, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'swap', ?, ?, 'pending', ?, ?)
        """,
        (
            user_ids["Omar Hassan"],
            user_ids["Aisha Rahman"],
            skill_ids[("Aisha Rahman", "Python programming", "offer")],
            skill_ids[("Omar Hassan", "Public speaking", "offer")],
            "I can help with presentation practice in return for Python basics.",
            "Monday evening",
            utc_now(),
            utc_now(),
        ),
    )
    db.commit()


app = create_app()


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", host="127.0.0.1", port=8000)
