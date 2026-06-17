# SkillMastery Write Paths

## Summary

`SkillMastery` is the single persisted per-user, per-skill score table in this codebase. It does not store score provenance or score history. All runtime writers use `update_or_create(user=user, skill=...)`, so newer writes overwrite the current row for that skill.

## Model

- File: `Backend/learning/models.py`
- Model: `SkillMastery`
- Key fields:
  - `user`
  - `skill`
  - `level_code`
  - `score`
  - `status`
  - `last_updated`
- Constraint: `unique_together = (("user", "skill"),)`

This means each user has at most one current `SkillMastery` row per skill.

## Runtime Writers

| File | Function | Skill updated | When it executes | Score source |
|---|---|---|---|---|
| `Backend/agents/services.py` | `evaluate_diagnostic` | `Grammar`, `Vocabulary` | Runs on `POST /api/diagnostic/evaluate/` via `DiagnosticEvaluateView` | Uses `diagnostic_result["skill_scores"]`. That result comes from valid LLM output if available, otherwise from the rule-based fallback built by `score_diagnostic_answers()` and `_build_rule_based_diagnostic_result()`. |
| `Backend/agents/voice_services.py` | `evaluate_pronunciation` | `Pronunciation` | Runs on `POST /api/voice-diagnostic/pronunciation/evaluate/` via `PronunciationEvaluateView` | Uses `comparison["score"]` from `compare_pronunciation()`, based on transcript-versus-target word matching. |
| `Backend/agents/voice_services.py` | `evaluate_listening` | `Listening` | Runs on `POST /api/voice-diagnostic/listening/evaluate/` via `ListeningEvaluateView` | Uses LLM score if `_evaluate_listening_with_llm()` returns valid data. Otherwise falls back to fixed rule-based bands: `90`, `70`, `40`, or `0`. |
| `Backend/agents/voice_services.py` | `evaluate_speaking` | `Speaking` | Runs on `POST /api/voice-diagnostic/speaking/evaluate/` via `SpeakingEvaluateView` | Uses heuristic score from `_evaluate_speaking_transcript()` based on transcript length, relevance terms, and simple phrase checks. |
| `Backend/agents/services.py` | `submit_teacher_feedback` | `session.module.skill` | Runs on `POST /api/teacher/feedback/` via `TeacherFeedbackView` after a lesson session exists | Uses LLM feedback score from `_teacher_feedback_from_llm()` if available, otherwise fallback score from `generate_teacher_feedback()`. |

## Test-Only Writers

These are not runtime application paths, but they do create `SkillMastery` rows directly in tests.

| File | Context | Skill updated | When it executes | Score source |
|---|---|---|---|---|
| `Backend/agents/tests.py` | `test_recommendation_and_dashboard_reuse_same_module` setup | `Grammar`, `Vocabulary`, `Listening`, `Speaking` | Test setup only | Hardcoded values `45`, `62`, `58`, `75` |
| `Backend/agents/tests.py` | Additional recommendation/plan setup | `Grammar`, `Speaking` | Test setup only | Hardcoded values `40`, `55` |

## Endpoint Triggers

- `POST /api/diagnostic/evaluate/`
  - View: `Backend/agents/views.py`
  - Service: `evaluate_diagnostic`
- `POST /api/voice-diagnostic/pronunciation/evaluate/`
  - View: `Backend/agents/voice_views.py`
  - Service: `evaluate_pronunciation`
- `POST /api/voice-diagnostic/listening/evaluate/`
  - View: `Backend/agents/voice_views.py`
  - Service: `evaluate_listening`
- `POST /api/voice-diagnostic/speaking/evaluate/`
  - View: `Backend/agents/voice_views.py`
  - Service: `evaluate_speaking`
- `POST /api/teacher/feedback/`
  - View: `Backend/agents/views.py`
  - Service: `submit_teacher_feedback`

## Key Finding

`SkillMastery` is a mixed-source table. It is written by:

- text diagnostic scoring
- pronunciation evaluation
- listening evaluation
- speaking evaluation
- teacher lesson feedback

Because all of these update the same per-user, per-skill row, the table does not reliably represent only diagnostic scores.

## Risk

Any endpoint that labels `SkillMastery` values as diagnostic-only scores is potentially misleading. The current recommendation flow reads from `SkillMastery`, so returned scores may actually come from lesson feedback or voice evaluations rather than the original diagnostic.

## Recommended Follow-Up

- Add score provenance fields to `SkillMastery`, such as `source` and `source_test_type`, or
- Store diagnostic results in a separate model/table and keep `SkillMastery` as a derived current-progress table, or
- Return both `current_skill_scores` and `diagnostic_scores` separately in APIs that need both concepts.

## Verification Note

For the MVP clarification update, the recommendation API and page were renamed to present these values as current skill scores while preserving backward compatibility by returning both `diagnostic_scores` and `current_skill_scores`.

During verification, backend tests were initially blocked by a broken import in `Backend/agents/services.py` and `Backend/agents/voice_services.py` that referenced `...documentation.llm_client`. The safe fix was to restore `Backend/agents/llm_client.py` and switch both modules back to local package imports.

Verification completed after that fix:

- Backend tests passed: `22/22`
- Frontend lint passed
- No database migrations were created
- Recommendation logic remained unchanged
- Weakest-skill selection remained unchanged
