# Voice and Audio Diagnostic Architecture

## Purpose

The current diagnostic is text-only. It can assess grammar, vocabulary, writing clarity, and sentence clarity because those skills are visible in written answers.

It should not numerically grade Speaking, Listening, or Pronunciation from text-only answers. Those skills require audio input, audio output, or both:

- Speaking requires observing a learner's spoken response.
- Listening requires checking comprehension after the learner hears audio.
- Pronunciation requires comparing a spoken repetition against a known target sentence.

This document defines the planned architecture for a future voice and audio diagnostic without implementing the feature yet.

## Skill Boundaries

Text-only diagnostic assesses:

- Grammar
- Vocabulary
- Writing clarity / sentence clarity

Voice/audio diagnostic will assess:

- Speaking
- Listening
- Pronunciation

Until voice/audio diagnostic is implemented, the text diagnostic should keep these statuses:

- Speaking: `Requires voice test`
- Listening: `Requires audio test`
- Pronunciation: `Requires voice test`

## Speaking Assessment

Pipeline:

```text
Prepared question
-> AI reads question using TTS
-> User records spoken answer
-> STT transcribes user audio
-> AI evaluates transcript
-> Update Speaking mastery
```

Assessment dimensions:

- Fluency
- Answer completeness
- Relevance to the question
- Sentence structure
- Spoken communication clarity

MVP evaluation can use the STT transcript as the main evidence. The scoring prompt should make clear that this is a speaking communication assessment, not a writing assessment, even though the transcript is text.

Example prompt:

```text
Question: Tell me about your daily routine.
Learner transcript: I wake up early and I go work then I study English.
```

Expected output:

- Speaking score
- Feedback
- Transcript-level correction or model answer
- Notes on fluency, relevance, completeness, and clarity

## Pronunciation Assessment

Pipeline:

```text
Prepared target sentence
-> AI reads target sentence using TTS
-> User repeats the sentence
-> STT transcribes user audio
-> Compare target sentence vs transcript
-> AI evaluates pronunciation clarity
-> Update Pronunciation mastery
```

Assessment dimensions:

- Word accuracy
- Missing words
- Substituted words
- Clarity of recognized speech

This should be described as pronunciation clarity, not full phonetic analysis. The MVP should avoid claiming to detect exact phonemes, stress, accent quality, mouth position, or detailed acoustic features unless a later provider/API explicitly supports that evidence.

Example:

```text
Target sentence: I want to improve my English pronunciation.
STT transcript: I want improve my English presentation.
```

The evaluator can compare:

- Missing word: `to`
- Substituted word: `pronunciation` -> `presentation`
- Overall clarity impact

## Listening Assessment

Pipeline:

```text
AI reads short passage using TTS
-> User listens
-> User answers comprehension question
-> AI evaluates answer accuracy
-> Update Listening mastery
```

Assessment dimensions:

- Comprehension accuracy
- Detail recall
- Ability to answer from heard audio

MVP listening should use short passages with one or two comprehension questions. The learner should not see the passage text before answering, otherwise the task becomes reading comprehension instead of listening comprehension.

Example passage:

```text
Maria works at a hospital. Yesterday, she helped three patients and studied English after dinner.
```

Example comprehension question:

```text
What did Maria do after dinner?
```

Expected answer:

```text
She studied English after dinner.
```

## Deepgram TTS/STT Plan

Use Deepgram Aura TTS for reading questions, target sentences, and listening passages.

Recommended TTS model/voice:

```text
aura-2-thalia-en
```

Important distinction:

- `aura-2-thalia-en` is for TTS.
- Do not use `aura-2-thalia-en` as the STT model.
- STT should use a separate Deepgram speech-to-text model configured by environment variable.

Planned environment variables:

```text
DEEPGRAM_API_KEY=
DEEPGRAM_TTS_MODEL=aura-2-thalia-en
DEEPGRAM_STT_MODEL=
USE_VOICE_DIAGNOSTIC=False
```

`USE_VOICE_DIAGNOSTIC` should gate all voice diagnostic endpoints and frontend entry points until the MVP is ready.

## Proposed Backend Endpoints

```text
GET  /api/voice-diagnostic/prompts/
POST /api/voice-diagnostic/tts/
POST /api/voice-diagnostic/pronunciation/evaluate/
POST /api/voice-diagnostic/speaking/evaluate/
POST /api/voice-diagnostic/listening/evaluate/
```

Endpoint responsibilities:

- `GET /api/voice-diagnostic/prompts/`: Return prepared prompts for Speaking, Listening, and Pronunciation.
- `POST /api/voice-diagnostic/tts/`: Generate or proxy TTS audio for a prompt, target sentence, or passage.
- `POST /api/voice-diagnostic/pronunciation/evaluate/`: Accept recorded audio or an audio reference, run STT, compare against target text, and update Pronunciation mastery.
- `POST /api/voice-diagnostic/speaking/evaluate/`: Accept recorded audio or an audio reference, run STT, evaluate spoken communication from the transcript, and update Speaking mastery.
- `POST /api/voice-diagnostic/listening/evaluate/`: Accept the learner's comprehension answer, evaluate it against the passage/question, and update Listening mastery.

For the MVP, keep endpoint responses aligned with the existing agent API style:

```json
{
  "success": true,
  "message": "Voice diagnostic evaluation completed.",
  "data": {
    "skill": "Speaking",
    "score": 72,
    "feedback": "Your answer was relevant and understandable, but it needs smoother sentence structure.",
    "updated_mastery": {
      "skill": "Speaking",
      "score": 72,
      "status": "Learning"
    }
  }
}
```

## Proposed Frontend Page

Future route:

```text
/voice-diagnostic
```

The page should show three cards:

- Speaking Test
- Listening Test
- Pronunciation Test

Each card should expose the basic workflow state:

- Not started
- Prompt loaded
- Audio playing
- Recording
- Uploading / evaluating
- Complete
- Error

Expected controls:

- Play prompt audio
- Start recording
- Stop recording
- Submit evaluation
- Retry

The page should stay behind `USE_VOICE_DIAGNOSTIC=False` until the backend endpoints and audio capture flow are ready.

## Database Recommendation

For MVP, reuse:

- `SkillMastery`

The evaluation endpoints can update Speaking, Listening, and Pronunciation mastery records the same way the text diagnostic updates Grammar and Vocabulary.

Optional future model:

```text
AssessmentAttempt
```

Suggested fields:

```text
user
assessment_type
prompt_text
target_text
user_transcript
audio_file
score
feedback
metadata JSON
created_at
```

Potential `assessment_type` values:

- `speaking`
- `listening`
- `pronunciation`

Use `metadata JSON` for provider details and structured evaluation artifacts such as missing words, substituted words, transcript confidence, passage ID, and prompt version.

## MVP Scope

MVP should include:

- Feature flag via `USE_VOICE_DIAGNOSTIC`
- Prepared prompts for the three voice/audio skills
- Deepgram Aura TTS for prompt playback
- STT transcription placeholder configured by `DEEPGRAM_STT_MODEL`
- Speaking evaluation from transcript
- Pronunciation clarity comparison from target sentence and transcript
- Listening comprehension evaluation from heard passage and learner answer
- `SkillMastery` updates for Speaking, Listening, and Pronunciation

MVP should not include:

- Full phonetic pronunciation analysis
- Accent scoring
- Real-time streaming audio feedback
- Long-form conversation assessment
- Permanent audio storage unless explicitly required
- Replacement of the existing text-only diagnostic

## Future Scope

Future iterations can add:

- `AssessmentAttempt` persistence
- Prompt versioning
- Audio file storage and retention rules
- STT confidence tracking
- More robust pronunciation clarity metrics
- Multi-question listening tests
- Progress history per voice/audio skill
- Admin-managed prompt banks
- Provider abstraction if Deepgram is replaced or supplemented

## Implementation Order

Recommended sequence:

1. Add feature flag and environment variables.
2. Add prompt definitions for Speaking, Listening, and Pronunciation.
3. Add Deepgram TTS service wrapper.
4. Add STT service wrapper using `DEEPGRAM_STT_MODEL`.
5. Add backend evaluation endpoints behind the feature flag.
6. Add `/voice-diagnostic` frontend route behind the feature flag.
7. Reuse `SkillMastery` for MVP score updates.
8. Add `AssessmentAttempt` only when attempt history, auditability, or audio retention becomes necessary.
