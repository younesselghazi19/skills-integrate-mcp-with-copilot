# Mergington High School Activities API

A FastAPI application that lets students view extracurricular activities and
manage their own signups.

## Features

- View activities and current participants
- Create student accounts and sign in
- Sign up for and unregister from activities as the authenticated student
- Provision a supervisor who can assign club administrators
- Enforce supervisor-only assignment APIs and club-scoped authorization for
  club routes

User accounts, sessions, and administrator assignments are stored in SQLite.
Activity data remains in memory and resets when the server restarts. Club
directory management is not included; the club-scoping dependency is intended
to protect those routes when that feature is added.

## Getting Started

1. Install the dependencies:

   ```
   pip install -r requirements.txt
   ```

2. Optionally configure an initial supervisor before starting the application:

   ```
   export INITIAL_SUPERVISOR_EMAIL=supervisor@mergington.edu
   export INITIAL_SUPERVISOR_PASSWORD='use-a-long-unique-password'
   ```

   Both variables must be set together. The password must contain at least 12
   characters. The initial supervisor is created only once; restarting the
   application does not reset its password.

3. Start the application:

   ```
   uvicorn app:app --app-dir src --reload
   ```

4. Open http://localhost:8000 in your browser. API documentation is available
   at http://localhost:8000/docs.

The database defaults to `src/school.db`. Set `DATABASE_PATH` to use another
location. Set `COOKIE_SECURE=true` when serving the application over HTTPS;
the session cookie is HttpOnly and SameSite=Lax.

## Account and Authorization API

| Method | Endpoint | Access |
| ------ | -------- | ------ |
| POST | `/auth/register` | Public; creates a student account |
| POST | `/auth/login` | Public; creates a session |
| POST | `/auth/logout` | Public; revokes the current session |
| GET | `/auth/me` | Signed-in user |
| GET | `/activities` | Public |
| POST | `/activities/{activity_name}/signup` | Signed-in student; signs up that account |
| DELETE | `/activities/{activity_name}/unregister` | Signed-in student; unregisters that account |
| GET | `/supervisor/club-assignments` | Supervisor |
| PUT | `/supervisor/club-assignments` | Supervisor; JSON body: `{"email":"admin@example.com","club_name":"Chess Club"}` |
| DELETE | `/supervisor/club-assignments` | Supervisor; same JSON body as assignment |

Public registration cannot select a role. Supervisors are provisioned through
the environment variables above and can promote student accounts by assigning
them to clubs. Removing a user's last club assignment returns their role to
student. The reusable club authorization dependency allows supervisors or an
administrator assigned to the requested club; other users are denied.

## Running Tests

Run the API tests with the Python standard library:

```
python -m unittest discover -s tests
```
