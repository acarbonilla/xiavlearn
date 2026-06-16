# Question-Aware Diagnostic Corrections

## Problem Found

The diagnostic agent sometimes gave weak or misleading corrections for low-quality answers.

- Question 1 could keep unclear self-introduction wording and only replace one fragment.
- Question 2 could mark a broken sentence as clear or leave the original sentence unchanged.
- Question 3 behaved better because the learner goal question naturally gave the model stronger context for a safe rewrite.

## Why Question 3 Worked Better

The learning-goal prompt is narrow and predictable. Even when the learner answer is unclear, the intended response shape is easier to infer:

- the answer should mention a learning goal
- the answer should describe improving English
- the answer should be one simple complete sentence

Questions 1 and 2 were broader, so weak LLM output could stay too close to the original broken sentence unless backend normalization stepped in.

## New Question-Aware Correction Rules

When an answer is broken, unclear, or contains nonsense patterns:

- the agent must not describe the answer as already clear or correct
- the agent must not reuse the original answer as `corrected_answer`
- the agent must use the question text to generate a safe fallback correction
- the agent must explicitly say the meaning is unclear
- the response must always include `feedback`, `corrected_answer`, and `mistakes`

Fallback correction patterns:

- Question 1: `My name is [Name]. I live in [place]. I am learning English to improve my communication skills.`
- Question 1 default: `My name is Jane Doe. I live in this city. I am learning English to improve my communication skills.`
- Question 2: `Yesterday, I practiced English and worked on my tasks.`
- Question 2 alternate: `Yesterday, I completed my work and continued practicing English.`
- Question 3: `My learning goal is to improve my English and communicate more clearly.`

Backend normalization now forces the fallback correction when:

- `corrected_answer` is copied from the learner answer for an unclear response
- `mistakes` is empty even though the correction changed
- feedback falsely claims the answer is already clear or correct

## Test Cases

Primary regression input:

```json
{
  "answers": [
    {
      "question": "Introduce yourself in English.",
      "answer": "Me I am with you , ohw with us."
    },
    {
      "question": "Describe what you did yesterday.",
      "answer": "Did I do not will be oyourss."
    },
    {
      "question": "What is your learning goal?",
      "answer": "Me goal to goal the goalingbowekng"
    }
  ]
}
```

Additional regression coverage:

- low-quality diagnostic answers must always produce real rewritten corrections
- copied LLM corrections must be replaced by question-aware fallbacks
- unclear answers must include mistakes and unclear feedback

## Expected Behavior

- Question 1 returns a real self-introduction.
- Question 2 returns a real yesterday sentence in past tense.
- Question 3 returns a real learning-goal sentence.
- No unclear answer is labeled as already clear, correct, and complete.
- Repeated original corrections are prevented.
- Mistake cards remain available in the frontend because `feedback`, `corrected_answer`, and `mistakes` are always populated.
