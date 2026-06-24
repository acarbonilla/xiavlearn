# XiAvLearn V5B-8 Realtime Voice Architecture

## Purpose

This document defines the V5B-8 realtime speech-to-text, AI text streaming, chunked teacher audio playback, interruption handling, and production hardening for voice conversation without replacing the stable V5A REST workflow.

V5A remains the production path for:

- starting a voice conversation session
- submitting manual transcripts
- uploading recorded audio for backend transcription
- generating teacher responses
- generating TTS audio when available
- reviewing saved conversation history

V5B extends the isolated realtime transport layer so the project can validate live STT, practice-only AI teacher text, practice-only teacher audio playback, and controlled barge-in while keeping V5A safe as the fallback production path.

## Scope

Implemented through V5B-8:

- authenticated per-session websocket access
- browser microphone chunk sending from the `/voice-conversation` experiment panel
- bounded base64 JSON audio chunk validation
- Deepgram live streaming STT adapter behind the websocket consumer
- partial and final transcript events from the backend to the frontend
- practice-only AI teacher response generation after final transcripts
- incremental AI text events from the backend to the frontend
- practice-only TTS generation after AI text completion
- chunked teacher audio events from the backend to the frontend
- frontend assembly and playback of realtime teacher audio
- explicit websocket interrupt events from frontend to backend
- backend cancellation or stale-marking of interrupted AI/TTS output
- learner-audio priority when a new utterance arrives during teacher output
- safe fallback to the existing V5A turn-based flow when realtime STT is unavailable
- per-connection websocket event and audio throughput limits
- idle timeout cleanup for stale microphone/websocket sessions
- server-side timeouts around realtime STT forwarding, AI generation, and TTS generation
- sanitized client-facing provider failures with server-side logging for the raw exception context
- retry-based turn persistence hardening to reduce duplicate turn-number race failures
- optional Redis-backed channel layer configuration for multi-worker deployments

Explicitly deferred:

- WebRTC
- `SkillMastery` updates from realtime events
- persistence of realtime transcript segments as conversation turns

## Relationship to V5A

V5B remains additive.

Design rules:

- V5A REST endpoints stay intact and usable.
- Realtime transport failure must not block the existing transcript/upload/record turn flow.
- Realtime sessions are practice-only.
- Final realtime transcripts may trigger practice-only teacher generation.
- Learner interruption must not corrupt the active websocket session.
- Interrupted AI/TTS output must not take priority over new learner audio.
- Realtime AI output must not update `SkillMastery`, CEFR unlocks, diagnostics, dashboard metrics, recommendations, or study plans.

## Connection Flow

Current V5B-8 flow:

```text
1. Client starts or selects a VoiceConversationSession through existing REST APIs.
2. Browser opens:
   /ws/voice-conversation/sessions/<session_id>/
3. Consumer authenticates the Django session cookie and checks session ownership.
4. Frontend asks for microphone permission only when the user starts the realtime test.
5. MediaRecorder emits small audio chunks.
6. Frontend base64-encodes each chunk and sends an audio_chunk websocket event.
7. Backend validates and acknowledges the chunk.
8. On the first audio chunk, backend opens a Deepgram live STT session.
9. Backend forwards audio bytes to Deepgram.
10. Backend emits:
    - stt_status
    - transcript_partial
    - transcript_final
11. When a final transcript arrives, backend generates a practice-only AI teacher response.
12. Backend emits:
    - ai_response_start
    - ai_response_delta
    - ai_response_final
13. After the AI text response completes, backend generates practice-only TTS audio.
14. Backend emits:
    - tts_audio_start
    - tts_audio_chunk
    - tts_audio_complete
15. If learner speech resumes or frontend sends `interrupt`, backend emits `assistant_interrupted`, stops local playback on the client, and cancels or ignores old AI/TTS output.
```

## Backend Components

Core files for V5B-6:

- `Backend/xiavlearn/asgi.py`
- `Backend/agents/consumers.py`
- `Backend/agents/realtime_protocol.py`
- `Backend/agents/realtime_stt.py`
- `Backend/agents/test_realtime_voice.py`
- `Backend/agents/voice_conversation_services.py`
- `Backend/xiavlearn/settings.py`
- `Backend/requirements.txt`

Frontend experiment files:

- `Frontend/src/app/voice-conversation/page.tsx`
- `Frontend/src/lib/api.ts`

## STT Provider Choice

Current choice: Deepgram live streaming STT through the official Python SDK.

Why:

- XiAvLearn already uses Deepgram for non-realtime STT and TTS.
- The official SDK provides websocket streaming helpers for live transcription.
- Listen v1 is the right fit for this phase because it supports partial transcripts, `send_keep_alive()`, and `send_finalize()`.

Implementation note:

- For browser `audio/webm` chunks, the backend forwards the decoded bytes without local transcoding.
- This is based on the Deepgram websocket contract making `encoding` optional for Listen v1. The backend only sets explicit encoding options when needed later.

## Safety Model

Current safeguards:

- websocket origin validation runs before auth/session handling
- unauthenticated users are rejected with close code `4401`
- non-owners are rejected with close code `4404`
- every audio chunk is size-checked before provider forwarding
- non-audio websocket chunk payloads are rejected before provider forwarding
- per-connection event and audio throughput limits close noisy clients with `4429`
- idle websocket sessions are closed automatically so microphone and provider resources are released
- realtime provider operations are bounded by server-side timeouts instead of waiting indefinitely
- raw provider and runtime exceptions stay in server logs and are replaced with safe public messages
- realtime STT failures surface as websocket status events instead of mutating persistent study state
- realtime AI failures surface as websocket AI error events instead of creating conversation turns
- realtime TTS failures surface as websocket TTS error events instead of mutating persistent study state
- interruption emits websocket-only control events and does not persist partial turns
- frontend fallbacks remain available even if realtime STT fails

## Current Protocol

Protocol version: `v5b-7`

### Server events

`connected`

```json
{
  "type": "connected",
  "session_id": 12,
  "protocol_version": "v5b-7",
  "realtime_stage": "persistence_fallback",
  "transport": "websocket",
  "message": "Realtime voice conversation socket connected."
}
```

`audio_chunk_ack`

```json
{
  "type": "audio_chunk_ack",
  "session_id": 12,
  "protocol_version": "v5b-7",
  "event_id": "chunk-1",
  "chunk_id": "chunk-1",
  "sequence": 1,
  "size_bytes": 3,
  "accepted": true,
  "ingest_stage": "base64_validated",
  "server_ts": "2026-06-25T00:00:12Z"
}
```

`stt_status`

```json
{
  "type": "stt_status",
  "session_id": 12,
  "protocol_version": "v5b-7",
  "provider": "deepgram",
  "state": "ready",
  "message": "Deepgram realtime STT stream connected.",
  "server_ts": "2026-06-25T00:00:12Z"
}
```

`transcript_partial`

```json
{
  "type": "transcript_partial",
  "session_id": 12,
  "protocol_version": "v5b-7",
  "provider": "deepgram",
  "transcript": "hello teacher",
  "is_final": false,
  "speech_final": false,
  "provider_event_type": "Results",
  "server_ts": "2026-06-25T00:00:13Z"
}
```

`transcript_final`

```json
{
  "type": "transcript_final",
  "session_id": 12,
  "protocol_version": "v5b-7",
  "provider": "deepgram",
  "transcript": "hello teacher today",
  "is_final": true,
  "speech_final": true,
  "provider_event_type": "Results",
  "server_ts": "2026-06-25T00:00:14Z"
}
```

`ai_response_start`

```json
{
  "type": "ai_response_start",
  "session_id": 12,
  "protocol_version": "v5b-7",
  "response_id": "ai-response-1",
  "practice_only": true,
  "transcript": "hello teacher today",
  "server_ts": "2026-06-25T00:00:15Z"
}
```

`ai_response_delta`

```json
{
  "type": "ai_response_delta",
  "session_id": 12,
  "protocol_version": "v5b-7",
  "response_id": "ai-response-1",
  "sequence": 1,
  "delta_text": "Practice feedback only: Good detail. ",
  "accumulated_text": "Practice feedback only: Good detail. ",
  "server_ts": "2026-06-25T00:00:15Z"
}
```

`ai_response_final`

```json
{
  "type": "ai_response_final",
  "session_id": 12,
  "protocol_version": "v5b-7",
  "response_id": "ai-response-1",
  "practice_only": true,
  "response_text": "Practice feedback only: Good detail. Teacher follow-up: What happened after that?",
  "response_source": "deterministic_fallback",
  "chunk_count": 2,
  "server_ts": "2026-06-25T00:00:15Z"
}
```

`tts_audio_start`

```json
{
  "type": "tts_audio_start",
  "session_id": 12,
  "protocol_version": "v5b-7",
  "response_id": "ai-response-1",
  "provider": "deepgram",
  "content_type": "audio/mpeg",
  "total_size_bytes": 17,
  "chunk_count": 1,
  "practice_only": true,
  "server_ts": "2026-06-25T00:00:16Z"
}
```

`tts_audio_chunk`

```json
{
  "type": "tts_audio_chunk",
  "session_id": 12,
  "protocol_version": "v5b-7",
  "response_id": "ai-response-1",
  "sequence": 1,
  "audio_base64": "ZmFrZS1yZWFsdGltZS10dHM=",
  "size_bytes": 17,
  "is_final": true,
  "server_ts": "2026-06-25T00:00:16Z"
}
```

`tts_audio_complete`

```json
{
  "type": "tts_audio_complete",
  "session_id": 12,
  "protocol_version": "v5b-7",
  "response_id": "ai-response-1",
  "provider": "deepgram",
  "content_type": "audio/mpeg",
  "total_size_bytes": 17,
  "chunk_count": 1,
  "practice_only": true,
  "server_ts": "2026-06-25T00:00:16Z"
}
```

`assistant_interrupted`

```json
{
  "type": "assistant_interrupted",
  "session_id": 12,
  "protocol_version": "v5b-7",
  "response_id": "ai-response-1",
  "trigger": "learner_audio",
  "reason": "Learner audio took priority over the current AI output.",
  "previous_state": "awaiting_playback_completion",
  "had_active_response": true,
  "stop_playback": true,
  "practice_only": true,
  "server_ts": "2026-06-25T00:00:17Z"
}
```

### Client events

`audio_chunk`

```json
{
  "type": "audio_chunk",
  "event_id": "chunk-1",
  "chunk_id": "chunk-1",
  "sequence": 1,
  "mime_type": "audio/webm",
  "size_bytes": 3,
  "duration_ms": 1000,
  "is_final": false,
  "audio_base64": "AQID"
}
```

`interrupt`

```json
{
  "type": "interrupt",
  "event_id": "interrupt-1",
  "source": "interrupt_button",
  "reason": "Learner interrupted the current AI output to speak again."
}
```

`assistant_playback_complete`

```json
{
  "type": "assistant_playback_complete",
  "event_id": "playback-2",
  "response_id": "ai-response-1"
}
```

## Validation Rules

Current payload rules:

- every websocket message must be a JSON object with a non-empty `type`
- `audio_chunk` requires `chunk_id`, `sequence`, `mime_type`, `size_bytes`, `duration_ms`, and `audio_base64`
- decoded base64 byte length must match `size_bytes`
- audio chunk size is capped at `1048576` bytes
- unsupported or malformed payloads return structured `error` events

## AI, TTS, And Interruption Notes

Current V5B-8 implementation details:

- teacher generation reuses the existing practice-only voice conversation response service
- websocket AI text streaming is incremental at the transport layer, but the backend still generates the full response before chunking it into small deltas
- realtime TTS reuses the existing Deepgram-based `synthesize_tts()` service used by the turn-based flow
- websocket teacher audio playback is chunked at the transport layer after the backend receives the completed TTS audio bytes
- interruption is websocket-based and controlled by frontend microphone restart or explicit interrupt button, not a production VAD model
- interrupted response ids are treated as stale so old AI/TTS events are ignored once learner speech retakes priority
- duplicate final transcripts are ignored briefly so provider replays do not create duplicate turns
- persistence retries help recover from concurrent turn-number collisions
- completed realtime exchanges are persisted into `VoiceConversationTurn` with `transcript_source = deepgram_streaming`
- persisted realtime turns carry `mode = realtime`, `service_version = v5b-7`, and `response_id` metadata
- frontend playback completion is reported with `assistant_playback_complete` so the backend can release the active teacher response cleanly

## Deployment Hardening

Recommended production configuration:

- keep V5A REST endpoints enabled because realtime remains an additive practice path, not the only voice path
- set `DEBUG=False`
- set explicit `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, and `CSRF_TRUSTED_ORIGINS`
- enable `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, and `SECURE_SSL_REDIRECT` behind HTTPS
- set `USE_X_FORWARDED_PROTO=True` when running behind a proxy that terminates TLS
- use `CHANNEL_REDIS_URL` so Channels can coordinate websocket state across multiple workers or instances
- keep `VOICE_CONVERSATION_REALTIME_*` limits and timeouts explicit in the environment for production tuning
- ensure `DEEPGRAM_API_KEY`, `LLM_API_KEY`, and any provider secrets are injected through environment variables only
- keep application logs for the `agents` logger so sanitized websocket failures can still be debugged server-side

Important note:

- protocol version remains `v5b-7`; V5B-8 hardens runtime behavior without requiring a new websocket message contract

## Recommended Next Steps

```text
V5B-9: optional production observability, browser automation coverage, and load testing
```

## Test Coverage and Current Limits

Covered by backend tests:

- authenticated owner can connect
- unauthenticated user is rejected
- non-owner is rejected
- chunk ack still works
- fake STT adapter can emit `stt_status`
- fake STT adapter can emit `transcript_partial`
- fake STT adapter can emit `transcript_final`
- final transcript can trigger `ai_response_start`
- backend can emit incremental `ai_response_delta` events
- backend can emit `ai_response_final`
- backend can emit `ai_response_error`
- backend can emit `tts_audio_start`
- backend can emit `tts_audio_chunk`
- backend can emit `tts_audio_complete`
- backend can emit `tts_audio_error`
- frontend or new learner audio can trigger `assistant_interrupted`
- successful realtime exchanges emit `realtime_turn_persisted`
- interrupted persisted exchanges emit `realtime_turn_interrupted`
- unavailable STT configuration returns `stt_status: unavailable`
- invalid base64 payloads are rejected
- client-facing realtime AI/TTS failures are sanitized
- rate-limited websocket clients are closed safely

Current limits:

- backend tests mock the STT adapter and do not hit Deepgram live services
- backend tests mock AI generation and do not hit external LLM services
- backend tests mock realtime TTS generation and do not hit Deepgram TTS directly
- frontend behavior is linted and built, but not browser-automation tested
- AI text streaming is transport-level chunking of a completed practice response, not provider-native token streaming
- teacher audio playback is transport-level chunking of a completed TTS response, not provider-native streaming audio
- interruption logic is controlled and session-scoped, but not backed by a full production VAD pipeline
- Redis-backed channel layers are configurable, but deployment infrastructure must provide the Redis service
