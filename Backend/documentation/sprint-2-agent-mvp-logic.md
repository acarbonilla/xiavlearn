# Sprint 2: Agent MVP Logic

Date: 2026-06-13

## Sprint Goal

Add an authenticated, rule-based backend workflow for diagnostic evaluation,
curriculum recommendation, guided study, feedback, scheduling, and coaching.
No external LLM is used in this sprint.

## Endpoints Added

- `POST /api/diagnostic/evaluate/`
  - Scores Grammar, Vocabulary, Speaking, Listening, and Pronunciation.
  - Updates `LearnerProfile.current_level`.
  - Creates or updates the user's `SkillMastery` records.
- `GET /api/curriculum/recommendation/`
  - Finds the user's weakest recorded skill.
  - Recommends an active module at the user's current level when available.
- `POST /api/teacher/session/`
  - Creates a `StudySession`.
  - Builds lesson text and one practice question from module data.
- `POST /api/teacher/feedback/`
  - Saves the learner answer, feedback, score, and completion time.
  - Updates mastery for the module skill.
- `POST /api/scheduler/generate-plan/`
  - Creates and saves a simple seven-day `StudyPlan`.
  - Focuses on up to two weakest skills.
- `GET /api/coach/summary/`
  - Summarizes the weakest skill and recent completed-session activity.
  - Returns a simple next step.
- `GET /api/dashboard/`
  - Now uses the curriculum recommendation service.
  - `recommended_module` is populated when an active module exists.

All Sprint 2 endpoints require authentication.

## Agent Responsibilities

- Diagnostic Agent: deterministic text heuristics, CEFR-level assignment, and
  mastery persistence.
- Curriculum Agent: weakest-skill lookup and active-module selection.
- Teacher Agent: lesson/session creation from stored module objectives.
- Feedback and Tracker Agent: simple error checks, scoring, session completion,
  and mastery updates.
- Scheduler Agent: weakest-skill weekly plan generation and persistence.
- Coach Agent: progress summary based on mastery and completed sessions.

Reusable logic is located in `agents/services.py`. API request validation and
HTTP responses are handled in `agents/views.py`.

## Rule-Based Limitation

The current scores and feedback are deterministic heuristics. They do not
measure speech audio, pronunciation quality, semantic correctness, or genuine
listening comprehension. Pronunciation and listening scores are text-based
proxies until audio exercises and an LLM or speech model are introduced.

If the exact weakest skill has no active module at the learner's level, the
recommendation service checks the next weakest mastered skill with a matching
module. It then falls back to another level for the weakest skill, an active
module at the current level, or the first available active module.

## How To Test

From `Backend`:

```powershell
.\.venv\Scripts\Activate.ps1
python manage.py check
python manage.py migrate
python manage.py seed_learning_data
python manage.py test agents
python manage.py runserver
```

Log in through `/admin/`, then test:

```text
POST /api/diagnostic/evaluate/
GET  /api/curriculum/recommendation/
POST /api/teacher/session/
POST /api/teacher/feedback/
POST /api/scheduler/generate-plan/
GET  /api/coach/summary/
GET  /api/dashboard/
```

Anonymous requests to the Sprint 2 endpoints should return `401` or `403`.

## Next Sprint Recommendation

Add a diagnostic question bank and response history, then introduce a
provider-neutral AI interface behind the existing service functions. Add audio
upload and transcription support before treating Listening and Pronunciation
scores as real proficiency measurements.
