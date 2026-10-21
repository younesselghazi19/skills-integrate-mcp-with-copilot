"""
High School Management System API

A FastAPI application that allows students to view and sign up for
extracurricular activities.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import sqlite3
from typing import Iterator

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


app = FastAPI(
    title="Mergington High School API",
    description="API for viewing and signing up for extracurricular activities",
)

current_dir = Path(__file__).parent
app.mount(
    "/static",
    StaticFiles(directory=str(current_dir / "static")),
    name="static",
)

DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", current_dir / "school.db"))
SESSION_COOKIE = "mergington_session"
SESSION_LIFETIME = timedelta(hours=12)
PASSWORD_ITERATIONS = 310_000
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"

activities = {
    "Chess Club": {
        "description": "Learn strategies and compete in chess tournaments",
        "schedule": "Fridays, 3:30 PM - 5:00 PM",
        "max_participants": 12,
        "participants": ["michael@mergington.edu", "daniel@mergington.edu"],
    },
    "Programming Class": {
        "description": "Learn programming fundamentals and build software projects",
        "schedule": "Tuesdays and Thursdays, 3:30 PM - 4:30 PM",
        "max_participants": 20,
        "participants": ["emma@mergington.edu", "sophia@mergington.edu"],
    },
    "Gym Class": {
        "description": "Physical education and sports activities",
        "schedule": "Mondays, Wednesdays, Fridays, 2:00 PM - 3:00 PM",
        "max_participants": 30,
        "participants": ["john@mergington.edu", "olivia@mergington.edu"],
    },
    "Soccer Team": {
        "description": "Join the school soccer team and compete in matches",
        "schedule": "Tuesdays and Thursdays, 4:00 PM - 5:30 PM",
        "max_participants": 22,
        "participants": ["liam@mergington.edu", "noah@mergington.edu"],
    },
    "Basketball Team": {
        "description": "Practice and play basketball with the school team",
        "schedule": "Wednesdays and Fridays, 3:30 PM - 5:00 PM",
        "max_participants": 15,
        "participants": ["ava@mergington.edu", "mia@mergington.edu"],
    },
    "Art Club": {
        "description": "Explore your creativity through painting and drawing",
        "schedule": "Thursdays, 3:30 PM - 5:00 PM",
        "max_participants": 15,
        "participants": ["amelia@mergington.edu", "harper@mergington.edu"],
    },
    "Drama Club": {
        "description": "Act, direct, and produce plays and performances",
        "schedule": "Mondays and Wednesdays, 4:00 PM - 5:30 PM",
        "max_participants": 20,
        "participants": ["ella@mergington.edu", "scarlett@mergington.edu"],
    },
    "Math Club": {
        "description": "Solve challenging problems and participate in math competitions",
        "schedule": "Tuesdays, 3:30 PM - 4:30 PM",
        "max_participants": 10,
        "participants": ["james@mergington.edu", "benjamin@mergington.edu"],
    },
    "Debate Team": {
        "description": "Develop public speaking and argumentation skills",
        "schedule": "Fridays, 4:00 PM - 5:30 PM",
        "max_participants": 12,
        "participants": ["charlotte@mergington.edu", "henry@mergington.edu"],
    },
}


class Credentials(BaseModel):
    email: str
    password: str


class ClubAdministratorAssignment(BaseModel):
    email: str
    club_name: str


@contextmanager
def get_database() -> Iterator[sqlite3.Connection]:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${password_hash.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    algorithm, iterations, salt_hex, expected_hash = stored_hash.split("$")
    if algorithm != "pbkdf2_sha256":
        return False
    actual_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        int(iterations),
    ).hex()
    return hmac.compare_digest(actual_hash, expected_hash)


def normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not EMAIL_PATTERN.fullmatch(normalized):
        raise HTTPException(status_code=422, detail="A valid email address is required")
    return normalized


def initialize_database() -> None:
    with get_database() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'student'
                    CHECK (role IN ('student', 'club_admin', 'supervisor')),
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS club_assignments (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                club_name TEXT NOT NULL,
                PRIMARY KEY (user_id, club_name)
            );
            """
        )

        supervisor_email = os.environ.get("INITIAL_SUPERVISOR_EMAIL")
        supervisor_password = os.environ.get("INITIAL_SUPERVISOR_PASSWORD")
        if bool(supervisor_email) != bool(supervisor_password):
            raise RuntimeError(
                "Set both INITIAL_SUPERVISOR_EMAIL and "
                "INITIAL_SUPERVISOR_PASSWORD to provision a supervisor."
            )
        if supervisor_email and supervisor_password:
            normalized_email = normalize_email(supervisor_email)
            if len(supervisor_password) < 12:
                raise RuntimeError(
                    "INITIAL_SUPERVISOR_PASSWORD must be at least 12 characters."
                )
            connection.execute(
                """
                INSERT OR IGNORE INTO users (email, password_hash, role, created_at)
                VALUES (?, ?, 'supervisor', ?)
                """,
                (
                    normalized_email,
                    hash_password(supervisor_password),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            user = connection.execute(
                "SELECT role FROM users WHERE email = ?", (normalized_email,)
            ).fetchone()
            if user["role"] != "supervisor":
                raise RuntimeError(
                    "The configured initial supervisor email is already "
                    "registered as a non-supervisor."
                )


initialize_database()


@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html")


def get_current_user(request: Request) -> dict | None:
    session_token = request.cookies.get(SESSION_COOKIE)
    if not session_token:
        return None

    token_hash = hashlib.sha256(session_token.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc)
    with get_database() as connection:
        session = connection.execute(
            """
            SELECT users.id, users.email, users.role, sessions.expires_at
            FROM sessions JOIN users ON users.id = sessions.user_id
            WHERE sessions.token_hash = ?
            """,
            (token_hash,),
        ).fetchone()
        if session is None:
            return None
        if datetime.fromisoformat(session["expires_at"]) <= now:
            connection.execute(
                "DELETE FROM sessions WHERE token_hash = ?", (token_hash,)
            )
            return None
        assignments = connection.execute(
            "SELECT club_name FROM club_assignments WHERE user_id = ?",
            (session["id"],),
        ).fetchall()
    return {
        "id": session["id"],
        "email": session["email"],
        "role": session["role"],
        "clubs": [assignment["club_name"] for assignment in assignments],
    }


def require_user(request: Request) -> dict:
    user = get_current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def require_supervisor(current_user: dict = Depends(require_user)) -> dict:
    if current_user["role"] != "supervisor":
        raise HTTPException(status_code=403, detail="Supervisor access required")
    return current_user


def require_club_admin(
    club_name: str, current_user: dict = Depends(require_user)
) -> dict:
    """Dependency for club routes: supervisors or that club's assigned admin."""
    if current_user["role"] == "supervisor":
        return current_user
    if (
        current_user["role"] != "club_admin"
        or club_name not in current_user["clubs"]
    ):
        raise HTTPException(status_code=403, detail="Club access denied")
    return current_user


@app.post("/auth/register", status_code=201)
def register(credentials: Credentials):
    email = normalize_email(credentials.email)
    if len(credentials.password) < 12:
        raise HTTPException(
            status_code=422,
            detail="Password must be at least 12 characters",
        )
    try:
        with get_database() as connection:
            connection.execute(
                """
                INSERT INTO users (email, password_hash, role, created_at)
                VALUES (?, ?, 'student', ?)
                """,
                (
                    email,
                    hash_password(credentials.password),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
    except sqlite3.IntegrityError as error:
        raise HTTPException(
            status_code=409, detail="An account with this email already exists"
        ) from error
    return {"message": "Account created. Please sign in."}


@app.post("/auth/login")
def login(credentials: Credentials, response: Response):
    email = normalize_email(credentials.email)
    with get_database() as connection:
        user = connection.execute(
            "SELECT id, password_hash FROM users WHERE email = ?", (email,)
        ).fetchone()
    if user is None or not verify_password(
        credentials.password, user["password_hash"]
    ):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    session_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(session_token.encode("utf-8")).hexdigest()
    expires_at = datetime.now(timezone.utc) + SESSION_LIFETIME
    with get_database() as connection:
        connection.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (token_hash, user["id"], expires_at.isoformat()),
        )
    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        max_age=int(SESSION_LIFETIME.total_seconds()),
        path="/",
    )
    return {"message": "Signed in"}


@app.post("/auth/logout")
def logout(request: Request, response: Response):
    session_token = request.cookies.get(SESSION_COOKIE)
    if session_token:
        token_hash = hashlib.sha256(session_token.encode("utf-8")).hexdigest()
        with get_database() as connection:
            connection.execute(
                "DELETE FROM sessions WHERE token_hash = ?", (token_hash,)
            )
    response.delete_cookie(key=SESSION_COOKIE, path="/", samesite="lax")
    return {"message": "Signed out"}


@app.get("/auth/me")
def get_me(current_user: dict = Depends(require_user)):
    return current_user


@app.get("/activities")
def get_activities():
    return activities


@app.post("/activities/{activity_name}/signup")
def signup_for_activity(
    activity_name: str, current_user: dict = Depends(require_user)
):
    """Sign up the authenticated student for an activity."""
    if current_user["role"] != "student":
        raise HTTPException(status_code=403, detail="Student access required")
    if activity_name not in activities:
        raise HTTPException(status_code=404, detail="Activity not found")

    activity = activities[activity_name]
    email = current_user["email"]
    if email in activity["participants"]:
        raise HTTPException(status_code=400, detail="Student is already signed up")

    activity["participants"].append(email)
    return {"message": f"Signed up {email} for {activity_name}"}


@app.delete("/activities/{activity_name}/unregister")
def unregister_from_activity(
    activity_name: str, current_user: dict = Depends(require_user)
):
    """Unregister the authenticated student from an activity."""
    if current_user["role"] != "student":
        raise HTTPException(status_code=403, detail="Student access required")
    if activity_name not in activities:
        raise HTTPException(status_code=404, detail="Activity not found")

    activity = activities[activity_name]
    email = current_user["email"]
    if email not in activity["participants"]:
        raise HTTPException(
            status_code=400,
            detail="Student is not signed up for this activity",
        )

    activity["participants"].remove(email)
    return {"message": f"Unregistered {email} from {activity_name}"}


@app.get("/supervisor/club-assignments")
def list_club_assignments(
    current_user: dict = Depends(require_supervisor),
):
    with get_database() as connection:
        assignments = connection.execute(
            """
            SELECT users.email, club_assignments.club_name
            FROM club_assignments
            JOIN users ON users.id = club_assignments.user_id
            ORDER BY club_assignments.club_name, users.email
            """
        ).fetchall()
    return [dict(assignment) for assignment in assignments]


@app.put("/supervisor/club-assignments", status_code=200)
def assign_club_administrator(
    assignment: ClubAdministratorAssignment,
    current_user: dict = Depends(require_supervisor),
):
    email = normalize_email(assignment.email)
    club_name = assignment.club_name.strip()
    if not club_name:
        raise HTTPException(status_code=422, detail="Club name is required")

    with get_database() as connection:
        user = connection.execute(
            "SELECT id, role FROM users WHERE email = ?", (email,)
        ).fetchone()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        if user["role"] == "supervisor":
            raise HTTPException(
                status_code=409,
                detail="Supervisors cannot be assigned as club administrators",
            )
        connection.execute(
            """
            INSERT OR IGNORE INTO club_assignments (user_id, club_name)
            VALUES (?, ?)
            """,
            (user["id"], club_name),
        )
        connection.execute(
            "UPDATE users SET role = 'club_admin' WHERE id = ?", (user["id"],)
        )
    return {"message": f"Assigned {email} to administer {club_name}"}


@app.delete("/supervisor/club-assignments")
def remove_club_administrator(
    assignment: ClubAdministratorAssignment,
    current_user: dict = Depends(require_supervisor),
):
    email = normalize_email(assignment.email)
    club_name = assignment.club_name.strip()
    with get_database() as connection:
        user = connection.execute(
            "SELECT id FROM users WHERE email = ?", (email,)
        ).fetchone()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        deleted = connection.execute(
            "DELETE FROM club_assignments WHERE user_id = ? AND club_name = ?",
            (user["id"], club_name),
        ).rowcount
        if not deleted:
            raise HTTPException(status_code=404, detail="Assignment not found")
        remaining = connection.execute(
            "SELECT 1 FROM club_assignments WHERE user_id = ? LIMIT 1",
            (user["id"],),
        ).fetchone()
        if remaining is None:
            connection.execute(
                "UPDATE users SET role = 'student' WHERE id = ?", (user["id"],)
            )
    return {"message": f"Removed {email} from {club_name}"}
