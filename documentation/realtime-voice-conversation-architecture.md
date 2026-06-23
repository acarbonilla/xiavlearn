# Realtime Voice Conversation Architecture

## Purpose

This document defines the V5B backend foundation for realtime voice conversation without replacing the existing V5A turn-based REST flow.

V5A remains the stable production path for:

- manual transcript turns
- audio upload plus Deepgram STT
- AI teacher text response
- TTS playback
- conversation history

V5B adds a separate realtime transport layer beside V5A so the team can evolve streaming features incrementally and safely.

## Scope of V5B-1

Implemented in this spike:

- architecture roadmap for V5B
- Django Channels WebSocket foundation
- authenticated per-session WebSocket connection
- basic connection, session status, heartbeat, and echo events
- ownership checks for `VoiceConversationSession`

Explicitly not implemented in V5B-1:

- live microphone streaming
- Deepgram live streaming STT
- realtime LLM provider calls
- streaming TTS
- interruption or barge-in behavior
- frontend realtime production UI
- official scoring or `SkillMastery` writes

## Recommended Roadmap

```text
V5B-1: Realtime architecture spike + WebSocket skeleton
V5B-2: Frontend microphone capture + WebSocket audio chunk sending
V5B-3: Streaming STT provider integration
V5B-4: Streaming AI response events
V5B-5: Streaming / chunked TTS playback
V5B-6: Interruption / barge-in support
V5B-7: Realtime session persistence + fallback to V5A
V5B-8: Production hardening: rate limits, timeouts, cleanup, observability
```

## Chosen Transport Strategy

### Current choice

Use authenticated WebSockets first.

Reasons:

- XiAvLearn already runs Django ASGI, so Channels is the smallest safe backend step.
- WebSockets are enough for server events, debug signaling, and the first streaming protocol.
- WebRTC can be evaluated later once media capture, NAT traversal, and interruption behavior become real requirements.

### Deferred choice

Do not introduce WebRTC in V5B-1.

Reasons:

- it adds significantly more transport and signaling complexity
- it is unnecessary before the application can already handle streaming text/audio events on the backend
- the project still needs provider streaming and interruption rules first

## Authentication and Privacy Model

The realtime route is bound to a specific `VoiceConversationSession`:

```text
/ws/voice-conversation/sessions/<session_id>/
```

Rules:

- the socket requires an authenticated Django user
- the user must own the `VoiceConversationSession`
- another user's session returns a websocket close without exposing session metadata
- the socket never writes `SkillMastery`
- the socket is practice-only, same as V5A

The current implementation uses Django session/cookie auth through `AuthMiddlewareStack`, which matches the existing browser-based REST auth model.

## Current Event Contract

### Server events

`connected`

```json
{
  "type": "connected",
  "session_id": 12,
  "message": "Realtime voice conversation socket connected."
}
```

`session_status`

```json
{
  "type": "session_status",
  "session": {
    "id": 12,
    "status": "active",
    "target_skill": "speaking",
    "cefr_level": "A2",
    "turn_count": 3,
    "practice_only": true,
    "realtime_stage": "skeleton"
  }
}
```

`heartbeat`

```json
{
  "type": "heartbeat",
  "session_id": 12,
  "status": "ok"
}
```

`echo`

```json
{
  "type": "echo",
  "session_id": 12,
  "payload": {
    "debug": true
  }
}
```

`error`

```json
{
  "type": "error",
  "code": "unsupported_message",
  "message": "Unsupported realtime message type."
}
```

### Client messages

Currently accepted:

- `{"type": "heartbeat"}`
- `{"type": "session_status"}`
- `{"type": "echo", "payload": {...}}`

## Planned Realtime Session Pipeline

Target future flow:

```text
browser microphone
-> client chunking / capture buffer
-> websocket event stream
-> streaming STT adapter
-> partial transcript events
-> streaming AI teacher response events
-> streaming TTS events
-> playback in frontend
-> interruption handling
-> persisted summary / fallback to V5A history
```

## Backend Separation from V5A

V5B must not replace V5A.

Design rule:

- V5A REST endpoints remain the source of truth for production turn-based practice
- V5B sockets are additive and can fail independently
- future realtime sessions should be able to fall back to V5A turn persistence when streaming is unavailable or interrupted

## Operational Notes for Later Tasks

### State model

Later realtime session state should track:

- socket connection status
- provider stream status
- partial transcript buffer
- current AI response buffer
- current TTS playback state
- interruption eligibility

### Production hardening targets

V5B-8 should cover:

- connection idle timeouts
- per-user rate limits
- chunk size validation
- provider retry policy
- explicit cleanup for abandoned streams
- structured logging and metrics
- backpressure handling

## Current Backend Files

V5B-1 introduces these core backend pieces:

- `Backend/xiavlearn/asgi.py`
- `Backend/xiavlearn/routing.py`
- `Backend/agents/routing.py`
- `Backend/agents/consumers.py`

This is intentionally minimal so future V5B tasks can evolve the protocol without destabilizing the V5A REST flow.
