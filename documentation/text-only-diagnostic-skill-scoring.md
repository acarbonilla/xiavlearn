# Text-Only Diagnostic Skill Scoring

## Why This Change Was Needed

The diagnostic flow uses written answers only. That means it can evaluate what appears in text, such as grammar, vocabulary, clarity, and sentence structure. It cannot accurately measure speaking, listening, or pronunciation without voice or audio input.

Showing numeric scores for speaking, listening, and pronunciation in a text-only flow was misleading because those skills were never directly observed.

## What Is Assessed Now

The current text-only diagnostic numerically scores:

- Grammar
- Vocabulary

Writing clarity and sentence structure still influence the feedback and level explanation, but they are expressed through per-answer feedback rather than separate numeric score bars.

## What Requires Future Audio or Voice Tests

The following skills are now marked as unassessed during the text-only diagnostic:

- Speaking: `Requires voice test`
- Listening: `Requires audio test`
- Pronunciation: `Requires voice test`

A future voice or audio diagnostic can add real scoring for those areas.

## Backend Response Change

The diagnostic API now returns assessment metadata alongside the evaluated scores:

```json
{
  "assessment_mode": "text_only",
  "assessed_skills": ["Grammar", "Vocabulary"],
  "unassessed_skills": ["Speaking", "Listening", "Pronunciation"],
  "skill_scores": {
    "Grammar": 29,
    "Vocabulary": 38
  },
  "skill_status": {
    "Grammar": "Assessed",
    "Vocabulary": "Assessed",
    "Speaking": "Requires voice test",
    "Listening": "Requires audio test",
    "Pronunciation": "Requires voice test"
  }
}
```

Backend behavior now follows these rules:

- Rule-based fallback scores only Grammar and Vocabulary.
- The LLM prompt explicitly instructs the model not to score Speaking, Listening, or Pronunciation numerically.
- If the LLM still returns numeric scores for unassessed skills, the backend sanitizes the response and keeps only Grammar and Vocabulary.
- `SkillMastery` is updated only for assessed skills.

## Frontend UI Change

The diagnostic results page now:

- shows progress cards only for assessed skills
- shows status cards for unassessed skills instead of percentages
- keeps the inline result explanation and answer feedback flow

Example unassessed display:

- Speaking: `Requires voice test`
- Listening: `Requires audio test`
- Pronunciation: `Requires voice test`

## Test Case Used

Submitted answers:

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

Expected and verified behavior:

- Grammar and Vocabulary receive scores.
- Speaking shows `Requires voice test`.
- Listening shows `Requires audio test`.
- Pronunciation shows `Requires voice test`.
- No numeric scores are returned or rendered for unassessed skills.
