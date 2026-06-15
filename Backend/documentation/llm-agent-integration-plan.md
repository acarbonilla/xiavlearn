# Optional LLM Agent Integration Plan

## Current Rule-Based MVP Status

XiAv Learn currently uses deterministic rule-based agent logic in `agents/services.py`.
The MVP can already:
- score diagnostic answers using heuristics
- generate teacher lesson prompts from module metadata
- generate teacher feedback from regex and answer-length rules
- generate coach summaries from learner progress records

This rule-based behavior remains the default and stable path.

## Optional LLM Mode

An optional LLM layer now sits in front of the existing rule-based logic.
The backend will attempt an LLM-generated JSON response for:
- diagnostic evaluation
- teacher lesson generation
- teacher feedback generation
- coach summary generation

If LLM mode is disabled or unavailable, the application falls back to the existing rule-based implementation automatically.

## Environment Variables

Add these settings to `Backend/.env`:

```env
LLM_PROVIDER=openai
LLM_API_KEY=
LLM_MODEL=
USE_LLM_AGENTS=False
```

Suggested model for this project:
- `gpt-5.4-mini`

Behavior:
- `USE_LLM_AGENTS=False` keeps the current MVP fully rule-based
- missing `LLM_API_KEY` disables LLM calls safely
- failed API calls do not break the backend
- invalid LLM JSON responses are ignored and replaced by the fallback logic

## Fallback Behavior

The fallback path is intentionally preserved in `agents/services.py`.
Each LLM-assisted service validates the returned JSON shape before using it.
If validation fails, XiAv Learn immediately uses the existing deterministic logic.

Fallback coverage:
- `evaluate_diagnostic()` falls back to `score_diagnostic_answers()`
- `create_teacher_session()` falls back to the current lesson template
- `submit_teacher_feedback()` falls back to `generate_teacher_feedback()`
- `get_coach_summary()` falls back to the current summary template

## Why Fallback Matters For Demo Stability

The project is still demo-oriented and must remain reliable even when:
- no API key is configured
- network access is unavailable
- the LLM provider is down or rate-limited
- the model returns malformed output
- costs need to be controlled during development

Keeping the rule-based MVP intact ensures the product remains usable in local demos, classroom testing, and backend verification without depending on live model availability.
