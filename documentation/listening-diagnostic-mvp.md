# Listening Diagnostic MVP

## Goal

Implement the Listening Diagnostic MVP for XiAv Learn.

The learner listens to a short English passage, answers a comprehension question, and receives a listening comprehension score. The backend evaluates the answer and updates only the Listening `SkillMastery`.

Speaking remains out of scope for this MVP.

## User Flow

```text
Open /voice-diagnostic
-> Listening Test section
-> User plays audio passage
-> User answers comprehension question
-> Submit answer
-> Backend evaluates comprehension
-> Listening SkillMastery updates
-> UI shows score and feedback
```

The question can be visible before submission, but the passage is intended to be heard through TTS instead of read as the main test input.

## Backend Endpoint

### `GET /api/voice-diagnostic/prompts/`

Returns voice diagnostic prompts for currently implemented voice/audio checks. The Listening payload includes the passage, question, and expected answer.

```json
{
  "success": true,
  "data": {
    "listening": {
      "passage": "Maria works in an office. Yesterday, she helped a customer solve a computer problem. After work, she studied English for thirty minutes.",
      "question": "What problem did Maria help solve?",
      "expected_answer": "A computer problem."
    }
  }
}
```

### `POST /api/voice-diagnostic/tts/`

The frontend reuses the existing TTS endpoint and sends the listening passage text.

If Deepgram TTS is configured, the backend returns playable audio. If TTS is unavailable, the backend returns a clear JSON error and the app stays usable.

### `POST /api/voice-diagnostic/listening/evaluate/`

Input:

```json
{
  "question": "What problem did Maria help solve?",
  "expected_answer": "A computer problem.",
  "user_answer": "She helped solve a computer problem."
}
```

Success response:

```json
{
  "success": true,
  "data": {
    "score": 90,
    "status": "Mastered",
    "feedback": "Correct. You understood the key detail from the audio passage.",
    "question": "What problem did Maria help solve?",
    "expected_answer": "A computer problem.",
    "user_answer": "She helped solve a computer problem."
  }
}
```

Validation errors return a standard API error envelope and do not update mastery.

## Frontend Behavior

Route:

```text
/voice-diagnostic
```

The page includes a Listening Test section with:

- `Play passage`
- visible comprehension question
- answer textarea
- `Submit Listening Answer`
- score
- status
- feedback
- submitted answer
- expected answer

If TTS fails, the page shows the backend error message. The learner can still see the question and can retry playback after configuration is fixed.

## Scoring Logic

The endpoint evaluates the learner answer against the expected answer.

MVP rule-based scoring:

- Full keyword match: `90`, `Mastered`
- Partial keyword match: `70`, `Learning`
- Non-empty answer with no key detail match: `40`, `Needs Review`
- Empty answer: validation error

For the current prompt, the key expected words are:

```text
computer problem
```

Example:

```text
She helped solve a computer problem.
```

This receives a high score because it includes both key details.

## LLM Fallback Behavior

The backend attempts optional LLM evaluation through the existing `call_llm_json` helper.

If `USE_LLM_AGENTS=True` and the LLM provider is configured, the LLM can return:

```json
{
  "score": 90,
  "feedback": "Correct. You understood the key detail from the audio passage."
}
```

If the LLM is disabled, unavailable, or returns invalid data, the backend falls back to rule-based keyword matching.

## SkillMastery Update

Only Listening mastery is updated by the Listening MVP.

The endpoint creates or updates:

```text
SkillMastery(user, skill=Listening)
```

It does not update Speaking, Pronunciation, Grammar, or Vocabulary.

## Known Limitations

- The MVP checks comprehension from a single short passage.
- The rule-based fallback uses keyword matching, not deep semantic grading.
- The passage text is available in the prompt payload because the frontend needs it for TTS.
- TTS must be configured for a true audio-first listening experience.
- The MVP does not persist listening attempts.
- Speaking diagnostic remains future work.
