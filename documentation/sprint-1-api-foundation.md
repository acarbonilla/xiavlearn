Date: 2026-06-13

Sprint Goal
- Build DRF-based API foundation exposing core learning models for frontend and future AI agents.

Endpoints Created
- GET /api/health/ — Health check
- GET /api/skills/ — List all skills (public)
- GET /api/levels/ — List CEFR curriculum levels ordered by sort_order (public)
- GET /api/modules/ — List active modules (filters: level_code, skill) (public)
- GET /api/modules/<id>/ — Module detail (public)
- GET /api/auth/me/ — Current authenticated user (protected)
- GET /api/profile/ — Get or create learner profile (protected)
- PATCH /api/profile/ — Update allowed profile fields (protected)
- GET /api/dashboard/ — Dashboard foundation (protected)

Serializers Created
- `SkillSerializer` (learning/serializers.py)
- `CurriculumLevelSerializer` (learning/serializers.py)
- `ModuleSerializer` (learning/serializers.py)
- `LearnerProfileSerializer` (learning/serializers.py)
- `SkillMasterySerializer` (learning/serializers.py)
- `StudySessionSerializer` (learning/serializers.py)
- `StudyPlanSerializer` (learning/serializers.py)
- `UserSerializer` (accounts/serializers.py)

Views Created
- `health_check` (learning/views.py) — AllowAny
- `ProfileView` (learning/views.py) — IsAuthenticated, auto-creates profile
- `SkillListView` (learning/views.py) — AllowAny
- `CurriculumLevelListView` (learning/views.py) — AllowAny
- `ModuleListView` (learning/views.py) — AllowAny (supports filters)
- `ModuleDetailView` (learning/views.py) — AllowAny
- `DashboardView` (learning/views.py) — IsAuthenticated
- `MeView` (accounts/views.py) — IsAuthenticated

Authentication & Permissions
- `REST_FRAMEWORK` in settings configured with Session and Basic auth and default `IsAuthenticated`.
- Public endpoints explicitly use `AllowAny`.
- Protected endpoints use `IsAuthenticated`.

Behavior Notes
- `GET /api/profile/` uses `get_or_create` to auto-create a `LearnerProfile` for authenticated users.
- `PATCH /api/profile/` allows updating `target_level`, `daily_study_minutes`, `learning_goal` but not `current_level`.
- `DashboardView` returns combined user data: `profile`, `skill_mastery`, `recommended_module` (null for Sprint 1), `latest_study_plan`, `recent_sessions`.

Testing Steps
1. Activate virtualenv and install requirements:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

2. Run Django checks and apply migrations:

```bash
python manage.py check
python manage.py makemigrations
python manage.py migrate
python manage.py seed_learning_data
python manage.py runserver
```

3. Test public endpoints (no auth required):
- GET /api/health/
- GET /api/skills/
- GET /api/levels/
- GET /api/modules/
- GET /api/modules/?level_code=A2
- GET /api/modules/?skill=Grammar

4. Test protected endpoints (login via admin or API auth):
- GET /api/auth/me/
- GET /api/profile/
- PATCH /api/profile/ with allowed fields
- GET /api/dashboard/

Known Limitations
- No AI agent logic or diagnostics in Sprint 1.
- `recommended_module` is `null`; recommendation logic planned for Sprint 2.
- Diagnostic evaluation endpoint not implemented.

Next Sprint (Sprint 2)
- Implement Agent MVP: diagnostic evaluation, automated level updates, recommendation engine, and recommended_module logic.

Files Changed
- learning/serializers.py (confirmed existing)
- learning/views.py (confirmed existing)
- learning/urls.py (confirmed existing)
- accounts/serializers.py (confirmed existing)
- accounts/views.py (confirmed existing)
- accounts/urls.py (confirmed existing)
- xiavlearn/urls.py (confirmed existing)
- documentation/sprint-1-api-foundation.md (new)

Status: Implementation completed in code; run the testing steps to verify in your environment.
