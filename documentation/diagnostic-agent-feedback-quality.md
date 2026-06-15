# Diagnostic Agent Feedback Quality

## Problem Found

The diagnostic agent feedback was too generic.
Weak or unclear learner answers could still receive language like `Strong response`, which is inaccurate and not educational.
This made the diagnostic result less trustworthy and less useful for beginner learners.

## Prompt Improvement

`Backend/agents/prompts.py` now instructs the LLM to:
- avoid overpraising weak answers
- be supportive but honest
- identify grammar, spelling, vocabulary, clarity, and sentence structure issues
- provide a corrected version of each answer
- explain mistakes in simple learner-friendly language
- explicitly say when an answer is unclear or nonsensical
- use CEFR-style level judgment
- return JSON only

## New Feedback Fields

Each `answer_feedback` item now includes:

```json
{
  "question": "string",
  "answer": "string",
  "feedback": "string",
  "corrected_answer": "string",
  "mistakes": [
    {
      "type": "Grammar | Spelling | Vocabulary | Clarity | Sentence Structure",
      "original": "string",
      "correction": "string",
      "explanation": "string"
    }
  ]
}
```

## Fallback Improvement

The rule-based fallback in `Backend/agents/services.py` was also improved.
It now:
- lowers scores for unclear or nonsensical answers
- adds corrected answers
- adds a `mistakes` array
- avoids calling weak answers strong
- gives a clearer A1 explanation when meaning and grammar break down

This keeps the backend useful even when the LLM is disabled or fails.

## Example Before And After

### Before

Answer:

```text
Hi Im me and you. Please be me why not.
```

Possible feedback:

```text
Strong response. Keep improving accuracy and detail for even better communication.
```

### After

Feedback now should be closer to:

```text
Your answer uses some English words, but the meaning is unclear. You need clearer complete sentences with more accurate grammar and word choice.
```

Corrected answer example:

```text
Hi, my name is [your name]. I am learning English to improve my communication skills.
```

Mistake examples:
- `Im` -> `I am`
- unclear phrase -> replaced with a complete sentence that communicates the intended idea

## Test Case

Used test answers:

```json
{
  "answers": [
    {
      "question": "Introduce yourself in English.",
      "answer": "Hi Im me and you. Please be me why not."
    },
    {
      "question": "Describe what you did yesterday.",
      "answer": "I did almost things look lakkee."
    },
    {
      "question": "What is your learning goal?",
      "answer": "me learng was to be enough hose."
    }
  ]
}
```

Expected behavior:
- no `Strong response` feedback
- low or beginner-level scores
- clear note that meaning is unclear
- corrected answers included
- specific mistake items returned

## Validation

Recommended checks:
- `python manage.py check`
- `python manage.py test agents`
