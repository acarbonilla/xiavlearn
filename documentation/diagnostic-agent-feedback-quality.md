# Diagnostic Agent Feedback Quality

## Problem Found

The diagnostic agent could sometimes return a `corrected_answer` that was identical to the learner's original answer, even when the answer still had grammar, spelling, clarity, sentence structure, or naturalness problems.

That is a bad learner experience because the UI shows a correction panel, but the learner receives no real correction. It also weakens trust in the diagnostic result because inaccurate praise and unchanged corrections suggest the answer was acceptable when it was not.

## Why Repeated Correction Is Bad

If the system repeats a broken sentence as the correction:

- the learner cannot see what should change
- the `mistakes` list becomes inconsistent or empty
- the feedback sounds generic instead of educational
- the frontend correction and mistake cards lose value

A correction should only match the original answer when the original answer is already clear, grammatical, natural, and complete.

## New Strict Correction Rules

`Backend/agents/prompts.py` now instructs the LLM to follow stricter rules:

- do not repeat the original answer as `corrected_answer` unless it is already correct
- rewrite the answer if it has grammar, spelling, vocabulary, sentence structure, clarity, or naturalness issues
- compare `answer` and `corrected_answer` for every item
- if they are identical, `mistakes` must be empty and feedback must clearly say the answer is already correct
- if they are different, `mistakes` must contain at least one item
- do not call a broken or unclear sentence clear and understandable
- preserve the learner's intended meaning when possible
- if the meaning is unclear, provide the most likely corrected version and say that the original meaning was unclear

## Backend Sanitization

`Backend/agents/services.py` now adds stricter backend validation through `normalize_answer_feedback(...)`.

That helper now:

- normalizes each `answer_feedback` item safely
- falls back to rule-based feedback when required fields are missing
- rejects copied `corrected_answer` values when the original answer still has obvious issues
- restores rule-based mistakes when the LLM returns an empty or weak `mistakes` array
- replaces generic or misleading feedback with honest fallback feedback

This keeps the frontend stable and prevents broken LLM structures from reaching the UI.

## Feedback Schema

Each `answer_feedback` item now supports:

```json
{
  "question": "string",
  "answer": "string",
  "feedback": "specific feedback",
  "corrected_answer": "corrected sentence",
  "mistakes": [
    {
      "type": "Grammar | Spelling | Vocabulary | Clarity | Sentence Structure | Naturalness",
      "original": "problem text",
      "correction": "corrected text",
      "explanation": "simple explanation"
    }
  ]
}
```

## Example Before And After

### Before

Original:

```text
I'm Jane Doe living in this city. I am currently working as I.T. Tech support in a large and international company that base in capital region.
```

Bad correction:

```text
I'm Jane Doe living in this city. I am currently working as I.T. Tech support in a large and international company that base in capital region.
```

### After

Expected correction style:

```text
I am Jane Doe, and I live in this city. I currently work as an IT technical support specialist in a large international company based in the capital region.
```

## Test Case

Used test answers:

```json
{
  "answers": [
    {
      "question": "Introduce yourself in English.",
      "answer": "I'm Jane Doe living in this city. I am currently working as I.T. Tech support in a large and international company that base in capital region."
    },
    {
      "question": "Describe what you did yesterday.",
      "answer": "I did was I did on what we did before and after thisss.. real thing most."
    },
    {
      "question": "What is your learning goal?",
      "answer": "Goal is the gola of others were are hosell making green."
    }
  ]
}
```

## Expected Behavior

- question 1 receives a real rewritten correction instead of a copied sentence
- question 2 receives a clearer corrected rewrite instead of the original text
- question 3 receives a clearer corrected rewrite instead of the original text
- `mistakes` includes concrete grammar, spelling, clarity, sentence structure, or naturalness items
- weak or unclear answers do not receive overpraising feedback
- the frontend still shows corrected answers and mistake cards without breaking

## Validation

Recommended checks:

- `python manage.py check`
- `python manage.py test agents`
