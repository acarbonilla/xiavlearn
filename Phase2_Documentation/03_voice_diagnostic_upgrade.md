# Voice Diagnostic Upgrade

## Purpose

The voice diagnostic evolved from a simple voice assessment into a structured official assessment flow with saved history, item-level scoring, and final next-step guidance.

Primary implementation files:

- `Backend/agents/voice_services.py`
- `Backend/agents/voice_views.py`
- `Backend/agents/models.py`
- `Frontend/src/app/voice-diagnostic/page.tsx`
- `Frontend/src/app/voice-diagnostic/history/page.tsx`
- `Frontend/src/app/voice-diagnostic/history/[id]/page.tsx`
- `Frontend/src/lib/api.ts`

## Phase 1: Step-by-Step Flow

Implemented flow:

```text
Intro
-> Pronunciation Assessment
-> Listening Assessment
-> Speaking Assessment
-> Results
```

The frontend step orchestration is implemented in `Frontend/src/app/voice-diagnostic/page.tsx`.

## Phase 2: Multi-Item Assessment

Implemented structure:

```text
Pronunciation: 3 items
Listening: 3 items
Speaking: 3 items
Final score = aggregate of item scores
SkillMastery updates from final aggregate score
```

Important rule:

- Item preview scoring exists for learner feedback.
- Official mastery is updated only from the final batch aggregate result.

## Phase 3: Session History

Implemented persistence:

```text
VoiceDiagnosticSession
VoiceDiagnosticItem
User can view voice diagnostic history
Item-level results are stored
History is private per user
```

These models are defined in `Backend/agents/models.py`.

## Phase 4: Scoring Rubrics

Implemented rubric categories:

### Pronunciation rubric

- Word accuracy
- Target completion
- Sequence accuracy
- Missing words
- Substitutions
- Extra words
- Clarity estimate

### Listening rubric

- Correct detail
- Question relevance
- Completeness
- Semantic match
- Clarity

### Speaking rubric

- Task relevance
- Completeness
- Clarity
- Grammar control
- Vocabulary range
- Coherence
- Fluency signal

Rubric evaluation and aggregation are implemented in `Backend/agents/voice_services.py`.

## Phase 5: Final Report and Learning Path Refresh

Implemented report sections:

```text
Voice Diagnostic Report
Official Mastery Updated
Recommended Focus
Why this focus?
Recommended Next Step
View Study Plan
View Recommendation
View Voice Diagnostic History
```

The final report API is currently:

```text
GET /api/voice-diagnostic/sessions/<id>/report/
```

## Final Voice Diagnostic Flow

Implemented flow:

```text
Complete Voice Diagnostic
-> Save VoiceDiagnosticSession
-> Save VoiceDiagnosticItem records
-> Update official SkillMastery
-> Show final report
-> Recommend lowest voice skill
-> Route to correct Voice Teacher Session
```

Tie-break order for voice focus is:

```text
Pronunciation
Listening
Speaking
```

## API / Backend Notes

- Prompt loading, preview scoring, batch scoring, and report generation live in `Backend/agents/voice_services.py`.
- Session/report endpoints live in `Backend/agents/voice_views.py`.
- Voice session routes are registered in `Backend/agents/urls.py`.
- Official voice recommendation routes currently map directly to:

```text
/pronunciation-teacher
/listening-teacher
/speaking-teacher
```

## Frontend Notes

- The learner flow lives in `Frontend/src/app/voice-diagnostic/page.tsx`.
- History list/detail pages live in `Frontend/src/app/voice-diagnostic/history`.
- API client support lives in `Frontend/src/lib/api.ts`.
- The final report screen now links directly to:

```text
/recommendation
/study-plan?refresh=1
/voice-diagnostic/history
/dashboard
```
