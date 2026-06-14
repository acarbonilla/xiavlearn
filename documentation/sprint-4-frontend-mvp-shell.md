# Sprint 4: Frontend MVP Shell and API Connection

## Frontend Stack

- Next.js 16 with the App Router
- TypeScript
- Tailwind CSS 4
- Native Fetch API
- Django session authentication with credentialed cross-origin requests

The frontend lives in `Frontend/`. Next.js requires React and React DOM as
runtime dependencies, but the application is structured and run as a Next.js
application rather than a standalone React/Vite project.

## Pages Created

| Route | Purpose |
| --- | --- |
| `/` | Landing page and multi-agent learning journey overview |
| `/login` | MVP Django Admin login/register placeholder |
| `/dashboard` | Level, mastery, recommendation, plan, sessions, and coach placeholder |
| `/diagnostic` | Three-question diagnostic form and evaluation results |
| `/recommendation` | Recommended curriculum module and reason |
| `/lesson/[moduleId]` | Teacher session, lesson content, and answer submission |
| `/feedback` | Lesson score, feedback, and updated mastery |
| `/study-plan` | Weekly plan generation and coach summary |

Shared UI components include the header, cards, buttons, and skill score cards.
All data-loading screens include loading and error states.

## API Endpoints Connected

The typed API client is located at `Frontend/src/lib/api.ts`.

- `GET /api/dashboard/`
- `POST /api/diagnostic/evaluate/`
- `GET /api/curriculum/recommendation/`
- `POST /api/teacher/session/`
- `POST /api/teacher/feedback/`
- `POST /api/scheduler/generate-plan/`
- `GET /api/coach/summary/`

Requests use `credentials: "include"` and send Django's CSRF token for POST
requests when the `csrftoken` cookie is available. The backend now allows
credentialed requests and trusts the two local frontend origins.

## Authentication and Known Limitations

- Sprint 4 does not include a dedicated frontend login or registration API.
- The learner must log in through Django Admin before opening protected pages.
- Use the same hostname for both applications so browser cookies are shared.
  The recommended URLs are `http://127.0.0.1:8000` for Django and
  `http://127.0.0.1:3000` for Next.js.
- Using `localhost` for one app and `127.0.0.1` for the other can prevent the
  Django session and CSRF cookies from being sent.
- Lesson feedback is passed to `/feedback` through browser `sessionStorage`.
  Reloading in a new tab without completing a lesson shows the empty state.
- The current backend agents use the existing rule-based MVP behavior.

## Run Locally

### Backend

```powershell
cd Backend
.\.venv\Scripts\Activate.ps1
python manage.py runserver 127.0.0.1:8000
```

If PowerShell activation is disabled, run:

```powershell
cd Backend
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

### Frontend

Next.js 16 requires Node.js 20.9 or newer.

```powershell
cd Frontend
npm install
npm run dev -- --hostname 127.0.0.1
```

Open `http://127.0.0.1:3000`.

The API base URL is configured in `Frontend/.env.local`:

```text
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

## Verification

The Sprint 4 implementation was checked with:

```powershell
cd Frontend
npm run lint
npm run build

cd ..\Backend
.\.venv\Scripts\python.exe manage.py test
```

The frontend lint and production build pass. The production build includes all
requested routes. All eight Django tests pass.

## Next Sprint Recommendation

Add first-class frontend authentication backed by dedicated login, logout, and
registration endpoints. Persist workflow navigation state on the backend,
replace the feedback `sessionStorage` handoff with a session detail endpoint,
and add browser-level tests for the complete diagnostic-to-study-plan journey.
