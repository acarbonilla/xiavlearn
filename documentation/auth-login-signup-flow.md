# XiAv Learn Authentication: Login and Signup Flow

**Date:** June 14, 2026

## Overview

XiAv Learn uses Django session authentication for normal learner accounts.
Users can register and log in through the Next.js frontend without using Django
Admin. Authentication requests include cookies and use Django CSRF protection.

## Backend Endpoints

### `GET /api/auth/csrf/`

Creates the Django CSRF cookie and returns the token used by frontend POST
requests.

### `POST /api/auth/register/`

Accepts `username`, `email`, and `password`. Registration:

- Creates a Django `User`.
- Creates the related `LearnerProfile`.
- Logs the new user into the Django session.
- Returns the authenticated user.

### `POST /api/auth/login/`

Accepts `username` and `password`, authenticates the credentials, and creates a
Django session.

### `POST /api/auth/logout/`

Ends the current Django session. The endpoint requires an authenticated user
and a valid CSRF token.

### `GET /api/auth/me/`

Returns the current authenticated user's `id`, `username`, and `email`.

Successful endpoints use:

```json
{
  "success": true,
  "data": {},
  "message": "Request completed."
}
```

Failures use:

```json
{
  "success": false,
  "error": "Error message."
}
```

## Frontend Flow

### Signup

The `/signup` page collects username, email, password, and password
confirmation. It validates matching passwords, registers the learner, and
redirects successful registrations to `/diagnostic`.

### Login

The `/login` page collects username and password. A successful login redirects
the learner to `/dashboard`.

### Logout

The shared header displays the current username and a Logout button while a
session is active. Logout ends the session and redirects to `/login`.

### API Client

`Frontend/src/lib/api.ts` provides:

- `getCsrfToken()`
- `loginUser()`
- `registerUser()`
- `logoutUser()`
- `getCurrentUser()`

All API requests use `credentials: "include"`. Before a non-GET request, the
client fetches a CSRF token when the CSRF cookie is not already available.

## Local Development

Start Django:

```bash
cd Backend
python manage.py runserver 0.0.0.0:8000
```

Start Next.js:

```bash
cd Frontend
npm install
npm run dev -- --hostname 0.0.0.0
```

For LAN testing at `192.168.1.11`, use:

```text
Frontend: http://192.168.1.11:3000
Backend:  http://192.168.1.11:8000
```

The frontend environment is:

```text
NEXT_PUBLIC_API_BASE_URL=http://192.168.1.11:8000
```

The same hostname should be used for both applications so browser session and
CSRF cookies are available to the frontend.

## Verification Flow

1. Open `/signup`.
2. Create a learner account.
3. Confirm redirect to `/diagnostic`.
4. Submit the diagnostic and confirm results appear without a page reload.
5. Open `/dashboard` and confirm learner data loads.
6. Log out from the header.
7. Confirm redirect to `/login`.
8. Log in with the same credentials.
9. Confirm redirect to `/dashboard`.

## Validation

- Django authentication and agent API tests pass.
- Frontend lint passes.
- Frontend production build passes.
- Login, registration, logout, current-user, diagnostic, and dashboard requests
  use the same Django session.
