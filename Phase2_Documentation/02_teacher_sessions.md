# Teacher Sessions

## Purpose

Teacher sessions give the learner guided practice after diagnostics identify weak skills. They are intended to reinforce learning, not to act as official reassessments.

## Completed Teacher Sessions

- Speaking Teacher Session
- Listening Teacher Session
- Pronunciation Teacher Session

Current frontend routes exist in:

- `Frontend/src/app/speaking-teacher/page.tsx`
- `Frontend/src/app/listening-teacher/page.tsx`
- `Frontend/src/app/pronunciation-teacher/page.tsx`

Related backend session logic lives primarily in:

- `Backend/agents/services.py`
- `Backend/agents/views.py`

## Practice-Only Rule

```text
Teacher Sessions are practice only.
Teacher Sessions must not update SkillMastery.
Teacher Sessions should save practice data only.
```

This rule is reflected in the current product messaging and test coverage.

## Voice Skill Routing

Current routing rules:

```text
Speaking weakness -> /speaking-teacher
Listening weakness -> /listening-teacher
Pronunciation weakness -> /pronunciation-teacher
Grammar weakness -> text teacher/module lesson
Vocabulary weakness -> text teacher/module lesson
```

Voice skill route mapping is defined in `Backend/agents/services.py`.

## Session Types

Current practice session types include:

```text
guided_teacher_session
speaking_teacher_session
listening_teacher_session
pronunciation_teacher_session
```

## Frontend Routes

```text
/speaking-teacher
/listening-teacher
/pronunciation-teacher
```

## Backend Data Rule

Practice session data is stored in session records such as:

```text
StudySession
LessonSession
LessonTurn
```

Use these labels for teacher sessions:

```text
Practice Score
Teacher Session
Final Practice Result
```

Avoid these labels for teacher sessions:

```text
Official Mastery Updated
Diagnostic Score
CEFR Unlocked
```

## Files Affected

- `Backend/agents/models.py`
- `Backend/agents/services.py`
- `Backend/agents/views.py`
- `Frontend/src/app/speaking-teacher/page.tsx`
- `Frontend/src/app/listening-teacher/page.tsx`
- `Frontend/src/app/pronunciation-teacher/page.tsx`
