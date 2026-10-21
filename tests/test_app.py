import asyncio
import copy
import json
import os
from http.cookies import SimpleCookie
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.parse import unquote, urlsplit


TEST_DIRECTORY = tempfile.TemporaryDirectory()
os.environ["DATABASE_PATH"] = str(Path(TEST_DIRECTORY.name) / "test.db")
os.environ["INITIAL_SUPERVISOR_EMAIL"] = "supervisor@mergington.edu"
os.environ["INITIAL_SUPERVISOR_PASSWORD"] = "supervisor-password-123"
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import app as api  # noqa: E402
from fastapi import Depends  # noqa: E402


INITIAL_ACTIVITIES = copy.deepcopy(api.activities)


class APIClient:
    def __init__(self):
        self.cookies = {}

    def request(self, method, url, payload=None):
        parsed_url = urlsplit(url)
        body = b"" if payload is None else json.dumps(payload).encode("utf-8")
        headers = [(b"host", b"testserver")]
        if payload is not None:
            headers.append((b"content-type", b"application/json"))
        if self.cookies:
            cookie_header = "; ".join(
                f"{name}={value}" for name, value in self.cookies.items()
            )
            headers.append((b"cookie", cookie_header.encode("latin-1")))

        messages = []
        body_sent = False
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": unquote(parsed_url.path),
            "raw_path": parsed_url.path.encode("ascii"),
            "query_string": parsed_url.query.encode("ascii"),
            "root_path": "",
            "headers": headers,
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "state": {},
        }

        async def receive():
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        async def send(message):
            messages.append(message)

        asyncio.run(api.app(scope, receive, send))
        response_start = next(message for message in messages if message["type"] == "http.response.start")
        response_body = b"".join(
            message.get("body", b"")
            for message in messages
            if message["type"] == "http.response.body"
        )
        response_headers = dict(response_start["headers"])
        set_cookie = response_headers.get(b"set-cookie")
        if set_cookie:
            cookie = SimpleCookie()
            cookie.load(set_cookie.decode("latin-1"))
            if cookie.get(api.SESSION_COOKIE):
                morsel = cookie[api.SESSION_COOKIE]
                if morsel.value:
                    self.cookies[api.SESSION_COOKIE] = morsel.value
                else:
                    self.cookies.pop(api.SESSION_COOKIE, None)
        return (
            response_start["status"],
            json.loads(response_body) if response_body else None,
            response_headers,
        )


def club_access_route(club_name: str, current_user=Depends(api.require_club_admin)):
    return {"club": club_name, "user": current_user["email"]}


api.app.add_api_route(
    "/test-clubs/{club_name}/manage",
    club_access_route,
    methods=["GET"],
    name="test_club_access",
)


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        with api.get_database() as connection:
            connection.execute("DELETE FROM sessions")
            connection.execute("DELETE FROM club_assignments")
            connection.execute("DELETE FROM users WHERE email != ?", (
                "supervisor@mergington.edu",
            ))
        api.activities.clear()
        api.activities.update(copy.deepcopy(INITIAL_ACTIVITIES))
        self.student = APIClient()
        self.supervisor = APIClient()

    def test_unauthenticated_requests_are_denied(self):
        self.assertEqual(self.student.request("GET", "/auth/me")[0], 401)
        self.assertEqual(
            self.student.request("POST", "/activities/Chess%20Club/signup")[0],
            401,
        )
        self.assertEqual(
            self.student.request(
                "DELETE", "/activities/Chess%20Club/unregister"
            )[0],
            401,
        )
        self.assertEqual(
            self.student.request("GET", "/supervisor/club-assignments")[0],
            401,
        )

    def test_student_signup_and_unregister_are_bound_to_account(self):
        status, _, _ = self.student.request(
            "POST",
            "/auth/register",
            {"email": "Student@mergington.edu", "password": "student-password-123"},
        )
        self.assertEqual(status, 201)
        status, _, headers = self.student.request(
            "POST",
            "/auth/login",
            {"email": "student@mergington.edu", "password": "student-password-123"},
        )
        self.assertEqual(status, 200)
        self.assertIn(b"httponly", headers[b"set-cookie"].lower())

        status, _, _ = self.student.request(
            "POST",
            "/activities/Chess%20Club/signup?email=victim%40mergington.edu",
        )
        self.assertEqual(status, 200)
        participants = api.activities["Chess Club"]["participants"]
        self.assertIn("student@mergington.edu", participants)
        self.assertNotIn("victim@mergington.edu", participants)

        status, _, _ = self.student.request(
            "DELETE",
            "/activities/Chess%20Club/unregister?email=michael%40mergington.edu",
        )
        self.assertEqual(status, 200)
        self.assertIn("michael@mergington.edu", participants)
        self.assertNotIn("student@mergington.edu", participants)

    def test_supervisor_assignment_and_club_scope_are_enforced(self):
        self.student.request(
            "POST",
            "/auth/register",
            {"email": "admin@mergington.edu", "password": "administrator-123"},
        )
        self.student.request(
            "POST",
            "/auth/login",
            {"email": "admin@mergington.edu", "password": "administrator-123"},
        )
        self.supervisor.request(
            "POST",
            "/auth/login",
            {
                "email": "supervisor@mergington.edu",
                "password": "supervisor-password-123",
            },
        )

        status, _, _ = self.supervisor.request(
            "PUT",
            "/supervisor/club-assignments",
            {"email": "admin@mergington.edu", "club_name": "Chess Club"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            self.student.request("GET", "/test-clubs/Chess%20Club/manage")[0],
            200,
        )
        self.assertEqual(
            self.student.request("GET", "/test-clubs/Drama%20Club/manage")[0],
            403,
        )
        self.assertEqual(
            self.student.request("POST", "/activities/Chess%20Club/signup")[0],
            403,
        )
        self.assertEqual(
            self.student.request("GET", "/supervisor/club-assignments")[0],
            403,
        )
        self.assertEqual(
            self.supervisor.request("POST", "/activities/Chess%20Club/signup")[0],
            403,
        )
        self.assertEqual(
            self.supervisor.request("GET", "/test-clubs/Drama%20Club/manage")[0],
            200,
        )


if __name__ == "__main__":
    unittest.main()
