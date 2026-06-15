# Diagnostic Agent Result Explanation

## Old Behavior

Previously, the diagnostic flow submitted the learner answers, saved the diagnostic result, and redirected the user away from the diagnostic page immediately.
The user did not see:
- why a level was assigned
- which answers were strong or weak
- which skills affected the recommendation

## New Behavior

The diagnostic flow now stays on the same page after submission.
Updated flow:

```text
Diagnostic form
-> Submit answers
-> Diagnostic Agent evaluates
-> Show result on same page
-> User chooses Dashboard or Recommendation
```

The page now displays:
- overall level
- skill scores
- weak skills
- recommendation
- level explanation
- per-answer feedback
- next step guidance

## Backend Response Fields

`POST /api/diagnostic/evaluate/` now returns:

```json
{
  "overall_level": "A2",
  "skill_scores": {
    "Grammar": 65,
    "Vocabulary": 70,
    "Speaking": 55,
    "Listening": 50,
    "Pronunciation": 60
  },
  "weak_skills": ["Speaking", "Grammar"],
  "recommendation": "Focus on Speaking and Grammar.",
  "level_explanation": "Your level is A2 because your answers show basic sentence control, but you need more detail and accuracy.",
  "answer_feedback": [
    {
      "question": "Introduce yourself in English.",
      "answer": "My name is Alfie...",
      "feedback": "Good basic introduction. Add more details to improve fluency."
    }
  ],
  "next_step": "Review your weak skills and start the recommended module."
}
```

## LLM-First With Fallback Design

The diagnostic agent now attempts LLM output first when `USE_LLM_AGENTS=True`.
Expected LLM-generated fields:
- `overall_level`
- `skill_scores`
- `weak_skills`
- `recommendation`
- `level_explanation`
- `answer_feedback`
- `next_step`

Fallback behavior:
- if `USE_LLM_AGENTS=False`, rule-based logic is used
- if the API key is missing, rule-based logic is used
- if the API call fails, rule-based logic is used
- if the JSON shape is invalid, rule-based logic is used for required fields

This preserves demo stability and prevents the diagnostic endpoint from failing when live model access is unavailable.

## Frontend Display Behavior

`Frontend/src/app/diagnostic/page.tsx` now:
- uses `event.preventDefault()`
- submits the answers asynchronously
- shows a loading state while evaluating
- keeps the user on the same page after submission
- renders the diagnostic explanation result inline
- provides action buttons for Dashboard and Recommendation

Buttons:
- `Continue to Dashboard`
- `View Recommended Lesson`

## Test Steps

### Fallback mode

1. Set `USE_LLM_AGENTS=False` in `Backend/.env`
2. Restart the backend
3. Open the diagnostic page
4. Submit all three answers
5. Confirm the page stays on `/diagnostic`
6. Confirm the diagnostic result appears inline with explanation and answer feedback

### LLM-enabled mode

1. Set these values in `Backend/.env`

```env
LLM_PROVIDER=openai
LLM_API_KEY=your_real_key
LLM_MODEL=gpt-5.4-mini
USE_LLM_AGENTS=True
```

2. Restart the backend
3. Submit the diagnostic again
4. Confirm the inline result still appears
5. Confirm the app still works if the API key is removed or invalidated

### Validation run

Recommended checks:
- `python manage.py check`
- `python manage.py migrate`
- `python manage.py test agents accounts`
- `npm run lint`
