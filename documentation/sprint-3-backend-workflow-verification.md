# Sprint 3: Backend Workflow Verification and Frontend Readiness

Date: 2026-06-13

## Sprint Goal

Stabilize the XiAv Learn backend before frontend development by verifying the
complete MVP workflow, adding an automated API smoke test, standardizing agent
responses, and enabling restricted local-development CORS.

## Full Backend Flow

```text
Diagnostic
  -> Curriculum Recommendation
  -> Teacher Session
  -> Teacher Feedback and Tracker
  -> Scheduler Plan
  -> Coach Summary
  -> Dashboard
```

The diagnostic creates five skill mastery records and updates the learner
level. Recommendation selects an active module. Teacher feedback completes a
study session and updates mastery. The scheduler saves a weekly plan. Coach and
dashboard responses then reflect the persisted workflow state.

## Endpoint List

Public:

- `GET /api/health/`
- `GET /api/skills/`
- `GET /api/levels/`
- `GET /api/modules/`
- `GET /api/modules/?level_code=A2`
- `GET /api/modules/?skill=Grammar`
- `GET /api/modules/<id>/`

Protected:

- `GET /api/auth/me/`
- `GET /api/profile/`
- `PATCH /api/profile/`
- `GET /api/dashboard/`
- `POST /api/diagnostic/evaluate/`
- `GET /api/curriculum/recommendation/`
- `POST /api/teacher/session/`
- `POST /api/teacher/feedback/`
- `POST /api/scheduler/generate-plan/`
- `GET /api/coach/summary/`

## Agent Response Contract

Successful Sprint 2 agent responses use:

```json
{
  "success": true,
  "data": {},
  "message": "Operation completed."
}
```

DRF errors use:

```json
{
  "success": false,
  "error": "Clear error message"
}
```

Sprint 1 success payloads remain unchanged to avoid a broad breaking API
change. The frontend should use the response envelope for the six agent
endpoints and the existing serializers for the public, account, profile, and
dashboard endpoints.

## Example Payloads

Diagnostic:

```json
{
  "answers": [
    {
      "question": "Introduce yourself in English.",
      "answer": "My name is Alfie and I live in Cebu."
    }
  ]
}
```

Teacher session:

```json
{
  "module_id": 1
}
```

Teacher feedback:

```json
{
  "session_id": 1,
  "answer": "Yesterday I go to mall."
}
```

Profile update:

```json
{
  "target_level": "B2",
  "daily_study_minutes": 30,
  "learning_goal": "Improve workplace English"
}
```

## Example Agent Response

```json
{
  "success": true,
  "data": {
    "score": 62,
    "feedback": "Good attempt. Review verb tense.",
    "updated_mastery": {
      "skill": "Grammar",
      "score": 62,
      "status": "Learning"
    }
  },
  "message": "Teacher feedback generated and progress updated."
}
```

## CORS Readiness

`django-cors-headers` is installed. Requests are allowed from:

```text
http://localhost:3000
http://127.0.0.1:3000
```

All other origins remain disallowed by default. The backend does not use
`CORS_ALLOW_ALL_ORIGINS`.

## Smoke Test Instructions

Create a normal Django user or superuser, start the backend, and set:

```powershell
$env:TEST_USERNAME = "your-username"
$env:TEST_PASSWORD = "your-password"
$env:API_BASE_URL = "http://127.0.0.1:8000"
python scripts/api_smoke_test.py
```

`API_BASE_URL` is optional and defaults to `http://127.0.0.1:8000`.

The script uses Basic Authentication and verifies:

- Public endpoint availability and module detail
- Current user and profile update
- Diagnostic scores and five persisted mastery records
- Curriculum recommendation
- Teacher session and feedback
- Updated skill mastery score
- Saved scheduler plan
- Coach summary
- Dashboard recommendation, plan, session, and mastery state

The script changes the test user's profile and creates or updates mastery,
session, and study plan records. Use a dedicated development test account.

## Known Limitations

- Diagnostic, teaching, feedback, scheduling, and coaching logic is rule-based.
- Listening and pronunciation are text-based proxy scores.
- Basic Authentication is suitable for smoke testing, not the final browser
  authentication design.
- Running the smoke test repeatedly creates additional study sessions and plans.
- Public and Sprint 1 success responses do not yet share the agent envelope.

## Next Sprint Recommendation

Build the frontend authentication and API client layer with explicit handling
for the agent response envelope. Add token-based authentication before
production use, and introduce frontend integration tests for the complete
learner journey.
