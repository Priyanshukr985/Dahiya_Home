from __future__ import annotations

import csv
import io
import os
import re
import secrets
import sqlite3
from datetime import date, datetime
from functools import wraps
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import psycopg
from flask import (
    Flask,
    flash,
    jsonify,
    make_response,
    abort,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from psycopg.rows import dict_row
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = Path(__file__).resolve().parent
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
DB_PATH = Path(
    os.environ.get("DATABASE_PATH")
    or os.environ.get("DB_PATH")
    or (BASE_DIR / "enquiries.db")
).resolve()
USING_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))
PHONE_PATTERN = re.compile(r"^\+?[0-9()\-\s.]{10,20}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
INSECURE_SECRET_KEY = "change-this-secret-key"
INSECURE_DEFAULT_ADMIN_PASSWORD = "admin123"
CSRF_SESSION_KEY = "_csrf_token"


def env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


DEBUG_MODE = env_flag("FLASK_DEBUG") or env_flag("DEBUG")
SECRET_KEY_FROM_ENV = os.environ.get("SECRET_KEY", "")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD", INSECURE_DEFAULT_ADMIN_PASSWORD if DEBUG_MODE else ""
)
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH", "")
STRICT_SECURITY = env_flag("STRICT_SECURITY")
RUNTIME_WARNINGS: list[str] = []
DERIVED_ADMIN_PASSWORD_HASH = ""

app = Flask(__name__)
app.config.update(
    SECRET_KEY=SECRET_KEY_FROM_ENV or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=env_flag("SESSION_COOKIE_SECURE"),
)
ALLOWED_STATUSES = {"new", "contacted", "visited", "closed"}
try:
    DISPLAY_TIMEZONE = ZoneInfo("Asia/Kolkata")
except ZoneInfoNotFoundError:
    DISPLAY_TIMEZONE = None


def get_connection() -> sqlite3.Connection | psycopg.Connection:
    if USING_POSTGRES:
        return psycopg.connect(DATABASE_URL, row_factory=dict_row)

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def db_query(query: str, params: tuple[Any, ...] = ()) -> str:
    if USING_POSTGRES:
        return query.replace("?", "%s")
    return query


def init_db() -> None:
    with get_connection() as connection:
        if USING_POSTGRES:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS enquiries (
                    id SERIAL PRIMARY KEY,
                    full_name TEXT NOT NULL,
                    phone_number TEXT NOT NULL,
                    email_address TEXT,
                    apartment_interest TEXT,
                    preferred_visit_date TEXT,
                    message TEXT,
                    notes TEXT,
                    source TEXT NOT NULL DEFAULT 'website_form',
                    status TEXT NOT NULL DEFAULT 'new',
                    created_at TEXT NOT NULL,
                    updated_at TEXT
                )
                """
            )
        else:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS enquiries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name TEXT NOT NULL,
                    phone_number TEXT NOT NULL,
                    email_address TEXT,
                    apartment_interest TEXT,
                    preferred_visit_date TEXT,
                    message TEXT,
                    notes TEXT,
                    source TEXT NOT NULL DEFAULT 'website_form',
                    status TEXT NOT NULL DEFAULT 'new',
                    created_at TEXT NOT NULL,
                    updated_at TEXT
                )
                """
            )
            existing_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(enquiries)")
            }
            if "notes" not in existing_columns:
                connection.execute("ALTER TABLE enquiries ADD COLUMN notes TEXT")
            if "source" not in existing_columns:
                connection.execute(
                    "ALTER TABLE enquiries ADD COLUMN source TEXT NOT NULL DEFAULT 'website_form'"
                )
            if "updated_at" not in existing_columns:
                connection.execute("ALTER TABLE enquiries ADD COLUMN updated_at TEXT")

        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_enquiries_status ON enquiries(status)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_enquiries_created_at ON enquiries(created_at)"
        )
        connection.commit()


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def validate_runtime_configuration() -> None:
    issues: list[str] = []
    global DERIVED_ADMIN_PASSWORD_HASH

    if SECRET_KEY_FROM_ENV in {"", INSECURE_SECRET_KEY}:
        issues.append("Set a strong SECRET_KEY environment variable.")

    if ADMIN_PASSWORD_HASH:
        pass
    elif ADMIN_PASSWORD:
        if ADMIN_PASSWORD == INSECURE_DEFAULT_ADMIN_PASSWORD:
            issues.append(
                "Replace the default admin password and configure ADMIN_PASSWORD_HASH."
            )
        DERIVED_ADMIN_PASSWORD_HASH = generate_password_hash(ADMIN_PASSWORD)
        issues.append(
            "ADMIN_PASSWORD is deprecated. Configure ADMIN_PASSWORD_HASH instead."
        )
    else:
        issues.append(
            "Configure ADMIN_PASSWORD_HASH with a generated password hash."
        )

    if not issues:
        return

    if STRICT_SECURITY:
        raise RuntimeError("Unsafe production configuration. " + " ".join(issues))

    if not ADMIN_PASSWORD_HASH and not ADMIN_PASSWORD:
        globals()["ADMIN_PASSWORD"] = INSECURE_DEFAULT_ADMIN_PASSWORD
        globals()["DERIVED_ADMIN_PASSWORD_HASH"] = generate_password_hash(
            INSECURE_DEFAULT_ADMIN_PASSWORD
        )
        issues.append(
            "Local fallback enabled: admin login temporarily uses a generated hash for 'admin123'."
        )

    RUNTIME_WARNINGS.extend(issues)


def validate_payload(payload: dict[str, Any]) -> tuple[dict[str, str], dict[str, Any]]:
    errors: dict[str, str] = {}

    full_name = normalize_text(payload.get("full_name"))
    phone_number = normalize_text(payload.get("phone_number"))
    email_address = normalize_text(payload.get("email_address"))
    apartment_interest = normalize_text(payload.get("apartment_interest"))
    preferred_visit_date = normalize_text(payload.get("preferred_visit_date"))
    message = normalize_text(payload.get("message"))

    if not full_name:
        errors["full_name"] = "Full name is required."
    elif len(full_name) > 120:
        errors["full_name"] = "Full name must be 120 characters or fewer."

    if not phone_number:
        errors["phone_number"] = "Phone number is required."
    elif not PHONE_PATTERN.fullmatch(phone_number):
        errors["phone_number"] = "Please enter a valid phone number."

    if email_address and not EMAIL_PATTERN.fullmatch(email_address):
        errors["email_address"] = "Please enter a valid email address."

    allowed_interests = {"", "2bhk", "3bhk", "4bhk", "5bhk", "not-sure"}
    if apartment_interest not in allowed_interests:
        errors["apartment_interest"] = "Please select a valid apartment interest."

    if preferred_visit_date:
        try:
            selected_date = date.fromisoformat(preferred_visit_date)
            if selected_date < date.today():
                errors["preferred_visit_date"] = "Preferred visit date cannot be in the past."
        except ValueError:
            errors["preferred_visit_date"] = "Please enter a valid visit date."

    if len(message) > 1000:
        errors["message"] = "Message cannot exceed 1000 characters."

    cleaned = {
        "full_name": full_name,
        "phone_number": phone_number,
        "email_address": email_address or None,
        "apartment_interest": apartment_interest or None,
        "preferred_visit_date": preferred_visit_date or None,
        "message": message or None,
        "source": "website_form",
    }
    return errors, cleaned


validate_runtime_configuration()
init_db()

for warning in RUNTIME_WARNINGS:
    print(f"[startup warning] {warning}")


def current_timestamp() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def format_display_datetime(value: str | None) -> str:
    if not value:
        return "Not available"

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value

    if DISPLAY_TIMEZONE is not None:
        parsed = parsed.astimezone(DISPLAY_TIMEZONE)

    return parsed.strftime("%d %b %Y, %I:%M %p")


def format_display_date(value: str | None) -> str:
    if not value:
        return "Not selected"

    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return value

    return parsed.strftime("%d %b %Y")


app.jinja_env.filters["display_datetime"] = format_display_datetime
app.jinja_env.filters["display_date"] = format_display_date


def generate_csrf_token() -> str:
    token = session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def validate_csrf_token(submitted_token: str | None) -> bool:
    session_token = session.get(CSRF_SESSION_KEY, "")
    return bool(submitted_token and session_token) and secrets.compare_digest(
        submitted_token, session_token
    )


app.jinja_env.globals["csrf_token"] = generate_csrf_token


def verify_admin_password(password: str) -> bool:
    active_hash = ADMIN_PASSWORD_HASH or DERIVED_ADMIN_PASSWORD_HASH
    return bool(active_hash) and check_password_hash(active_hash, password)


def get_enquiry_or_404(enquiry_id: int) -> Any:
    with get_connection() as connection:
        enquiry = connection.execute(
            db_query(
                """
                SELECT id, full_name, phone_number, email_address, apartment_interest,
                       preferred_visit_date, message, notes, source, status,
                       created_at, updated_at
                FROM enquiries
                WHERE id = ?
                """
            ),
            (enquiry_id,),
        ).fetchone()

    if enquiry is None:
        abort(404)

    return enquiry


def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return view_func(*args, **kwargs)

    return wrapped_view


@app.before_request
def protect_admin_post_routes() -> None:
    if request.method != "POST" or not request.path.startswith("/admin/"):
        return

    if not validate_csrf_token(request.form.get("csrf_token")):
        abort(400, description="Invalid or missing CSRF token.")


@app.get("/")
def index() -> Any:
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/styles.css")
def styles() -> Any:
    return send_from_directory(BASE_DIR, "styles.css")


@app.get("/script.js")
def scripts() -> Any:
    return send_from_directory(BASE_DIR, "script.js")


@app.get("/assets/<path:filename>")
def asset_files(filename: str) -> Any:
    return send_from_directory(BASE_DIR / "assets", filename)


@app.get("/admin-assets/<path:filename>")
def admin_assets(filename: str) -> Any:
    return send_from_directory(BASE_DIR / "admin", filename)


@app.get("/api/health")
def health() -> Any:
    return jsonify({"success": True, "status": "ok"})


@app.post("/api/enquiries")
def create_enquiry() -> Any:
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"success": False, "error": "Invalid request body."}), 400

    errors, cleaned = validate_payload(payload)
    if errors:
        return jsonify({"success": False, "errors": errors}), 400

    created_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    with get_connection() as connection:
        insert_params = (
            cleaned["full_name"],
            cleaned["phone_number"],
            cleaned["email_address"],
            cleaned["apartment_interest"],
            cleaned["preferred_visit_date"],
            cleaned["message"],
            created_at,
        )
        if USING_POSTGRES:
            cursor = connection.execute(
                db_query(
                    """
                    INSERT INTO enquiries (
                        full_name,
                        phone_number,
                        email_address,
                        apartment_interest,
                        preferred_visit_date,
                        message,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    RETURNING id
                    """
                ),
                insert_params,
            )
            enquiry_id = cursor.fetchone()["id"]
        else:
            cursor = connection.execute(
                db_query(
                    """
                    INSERT INTO enquiries (
                        full_name,
                        phone_number,
                        email_address,
                        apartment_interest,
                        preferred_visit_date,
                        message,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """
                ),
                insert_params,
            )
            enquiry_id = cursor.lastrowid
        connection.commit()

    return (
        jsonify(
            {
                "success": True,
                "message": "Enquiry submitted successfully.",
                "enquiry_id": enquiry_id,
            }
        ),
        201,
    )


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login() -> Any:
    if session.get("admin_logged_in"):
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        username = normalize_text(request.form.get("username"))
        password = request.form.get("password") or ""

        if username == ADMIN_USERNAME and verify_admin_password(password):
            session.clear()
            session["admin_logged_in"] = True
            session["admin_username"] = username
            return redirect(url_for("admin_dashboard"))

        flash("Invalid username or password.", "error")

    return render_template("admin/login.html")


@app.get("/admin")
@login_required
def admin_dashboard() -> Any:
    search = normalize_text(request.args.get("search"))
    status = normalize_text(request.args.get("status"))
    apartment_interest = normalize_text(request.args.get("apartment_interest"))

    query = """
        SELECT id, full_name, phone_number, email_address, apartment_interest,
               preferred_visit_date, message, notes, source, status,
               created_at, updated_at
        FROM enquiries
    """
    conditions: list[str] = []
    params: list[Any] = []

    if search:
        conditions.append(
            "(full_name LIKE ? OR phone_number LIKE ? OR COALESCE(email_address, '') LIKE ?)"
        )
        search_term = f"%{search}%"
        params.extend([search_term, search_term, search_term])

    if status:
        conditions.append("status = ?")
        params.append(status)

    if apartment_interest:
        conditions.append("COALESCE(apartment_interest, '') = ?")
        params.append(apartment_interest)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY created_at DESC, id DESC"

    with get_connection() as connection:
        enquiries = connection.execute(db_query(query), params).fetchall()
        summary = connection.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'new' THEN 1 ELSE 0 END) AS new_count,
                SUM(CASE WHEN status = 'contacted' THEN 1 ELSE 0 END) AS contacted_count,
                SUM(CASE WHEN status = 'visited' THEN 1 ELSE 0 END) AS visited_count,
                SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END) AS closed_count
            FROM enquiries
            """
        ).fetchone()

    return render_template(
        "admin/dashboard.html",
        enquiries=enquiries,
        search=search,
        current_status=status,
        current_apartment_interest=apartment_interest,
        summary=summary,
        admin_username=session.get("admin_username", ADMIN_USERNAME),
    )


@app.post("/admin/enquiries/<int:enquiry_id>/status")
@login_required
def update_enquiry_status(enquiry_id: int) -> Any:
    next_status = normalize_text(request.form.get("status"))
    if next_status not in ALLOWED_STATUSES:
        flash("Invalid status selected.", "error")
        return redirect(url_for("admin_dashboard"))

    with get_connection() as connection:
        connection.execute(
            db_query("UPDATE enquiries SET status = ?, updated_at = ? WHERE id = ?"),
            (next_status, current_timestamp(), enquiry_id),
        )
        connection.commit()

    flash("Lead status updated.", "success")
    return redirect(request.referrer or url_for("admin_dashboard"))


@app.get("/admin/enquiries/<int:enquiry_id>")
@login_required
def admin_enquiry_detail(enquiry_id: int) -> Any:
    enquiry = get_enquiry_or_404(enquiry_id)
    return render_template("admin/enquiry_detail.html", enquiry=enquiry)


@app.post("/admin/enquiries/<int:enquiry_id>/notes")
@login_required
def update_enquiry_notes(enquiry_id: int) -> Any:
    notes = normalize_text(request.form.get("notes"))
    if len(notes) > 5000:
        flash("Notes cannot exceed 5000 characters.", "error")
        return redirect(url_for("admin_enquiry_detail", enquiry_id=enquiry_id))

    with get_connection() as connection:
        connection.execute(
            db_query("UPDATE enquiries SET notes = ?, updated_at = ? WHERE id = ?"),
            (notes or None, current_timestamp(), enquiry_id),
        )
        connection.commit()

    flash("Notes saved.", "success")
    return redirect(url_for("admin_enquiry_detail", enquiry_id=enquiry_id))


@app.post("/admin/enquiries/<int:enquiry_id>/delete")
@login_required
def delete_enquiry(enquiry_id: int) -> Any:
    with get_connection() as connection:
        connection.execute(db_query("DELETE FROM enquiries WHERE id = ?"), (enquiry_id,))
        connection.commit()

    flash("Lead deleted.", "success")
    return redirect(url_for("admin_dashboard"))


@app.get("/admin/export.csv")
@login_required
def export_enquiries() -> Any:
    with get_connection() as connection:
        enquiries = connection.execute(
            db_query(
                """
                SELECT id, full_name, phone_number, email_address, apartment_interest,
                       preferred_visit_date, message, notes, source, status,
                       created_at, updated_at
                FROM enquiries
                ORDER BY created_at DESC, id DESC
                """
            )
        ).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "id",
            "full_name",
            "phone_number",
            "email_address",
            "apartment_interest",
            "preferred_visit_date",
            "message",
            "notes",
            "source",
            "status",
            "created_at",
            "updated_at",
        ]
    )

    for enquiry in enquiries:
        writer.writerow([enquiry[column] for column in enquiry.keys()])

    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = (
        "attachment; filename=enquiries-export.csv"
    )
    return response


@app.get("/admin/logout")
@login_required
def admin_logout() -> Any:
    session.clear()
    return redirect(url_for("admin_login"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=DEBUG_MODE)
