# Pronunciation Diagnostic MVP

## Goal

Implement the first voice-based diagnostic for XiAv Learn: Pronunciation.

The learner listens to a target sentence, records themselves repeating it, and submits the recording. The backend transcribes the audio with Deepgram STT, compares the transcript against the target sentence, scores pronunciation clarity, and updates only the Pronunciation `SkillMastery`.

This MVP does not implement Speaking or Listening diagnostics.

## User Flow

1. The learner logs in.
2. The learner opens `/voice-diagnostic`.
3. The page loads the pronunciation target sentence:

```text
I want to improve my English communication skills for work and daily conversations.
```

4. The learner clicks `Play sentence`.
5. The frontend requests TTS from the backend.
6. If Deepgram TTS is configured, the browser plays the generated audio.
7. If TTS is not configured, the page shows a clear error and stays usable.
8. The learner clicks `Start recording`.
9. The browser records microphone audio with the MediaRecorder API.
10. The learner clicks `Stop recording`.
11. The learner clicks `Submit recording`.
12. The backend transcribes the audio, compares words, updates Pronunciation mastery, and returns the result.
13. The page shows transcript, score, feedback, missing words, and extra words.

## Backend Endpoints

### `GET /api/voice-diagnostic/prompts/`

Returns the pronunciation prompt.

```json
{
  "success": true,
  "data": {
    "pronunciation": {
      "target_sentence": "I want to improve my English communication skills for work and daily conversations."
    }
  }
}
```

### `POST /api/voice-diagnostic/tts/`

Input:

```json
{
  "text": "I want to improve my English communication skills for work and daily conversations."
}
```

Behavior:

- If `USE_VOICE_DIAGNOSTIC=True` and `DEEPGRAM_API_KEY` exists, call Deepgram Aura TTS.
- If TTS is not configured, return a safe JSON error.
- Deepgram failures return a clear JSON error.
- The backend must not crash when TTS is unavailable.

Safe fallback response:

```json
{
  "success": false,
  "error": "TTS is not configured yet."
}
```

### `POST /api/voice-diagnostic/pronunciation/evaluate/`

Input:

```text
multipart/form-data
audio_file
target_sentence
```

Behavior:

- If Deepgram STT is configured, transcribe `audio_file`.
- If STT is not configured, return a safe JSON error.
- Compare the transcript against `target_sentence`.
- Score pronunciation clarity using word match percentage.
- Update `SkillMastery` for Pronunciation only.
- Return transcript, score, status, feedback, word accuracy, missing words, extra words, and substituted words.

Example success response:

```json
{
  "success": true,
  "data": {
    "target_sentence": "I want to improve my English communication skills for work and daily conversations.",
    "transcript": "I want to improve my English skills for work and daily conversations.",
    "score": 91,
    "status": "Mastered",
    "feedback": "Your pronunciation clarity was strong and most words were recognized correctly.",
    "word_accuracy": 91,
    "missing_words": ["communication"],
    "extra_words": [],
    "substituted_words": []
  }
}
```

## Frontend Page

Route:

```text
/voice-diagnostic
```

The page includes:

- Title: `Voice Diagnostic`
- Section: `Pronunciation Test`
- Target sentence display
- `Play sentence`
- `Start recording`
- `Stop recording`
- `Submit recording`
- Transcript result
- Score and status
- Feedback
- Missing words
- Extra words

The page uses the browser MediaRecorder API for microphone recording. If the browser does not support MediaRecorder or microphone access is denied, the page shows a clear error.

## Deepgram TTS/STT Notes

Environment variables:

```text
DEEPGRAM_API_KEY=
DEEPGRAM_TTS_MODEL=aura-2-thalia-en
DEEPGRAM_STT_MODEL=nova-2
USE_VOICE_DIAGNOSTIC=False
```

Important:

- `aura-2-thalia-en` is a Deepgram Aura TTS voice.
- Do not use `aura-2-thalia-en` as the STT model.
- The MVP uses `DEEPGRAM_STT_MODEL=nova-2` for speech-to-text.
- `USE_VOICE_DIAGNOSTIC=False` keeps Deepgram-dependent behavior disabled by default.

## Fallback Behavior

The backend returns clear JSON errors for missing or unavailable voice services:

- Missing TTS config: `TTS is not configured yet.`
- Missing STT config: `Speech-to-text is not configured yet.`
- Deepgram request failure: `TTS request failed: ...` or `Speech-to-text request failed: ...`
- Missing upload: `audio_file is required.`
- Missing target sentence: `target_sentence must be a non-empty string.`

These errors should not affect the existing text diagnostic.

## Known Limitations

- This is pronunciation clarity, not full phonetic analysis.
- The score is based on recognized word overlap between target sentence and STT transcript.
- Accent, stress, intonation, phoneme-level accuracy, and acoustic quality are not scored.
- MediaRecorder support varies by browser and requires microphone permission.
- TTS playback depends on Deepgram configuration.
- STT evaluation depends on Deepgram configuration.
- Audio files are not persisted in the MVP.
- Speaking and Listening diagnostics are still future work.
