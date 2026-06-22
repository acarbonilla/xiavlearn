# V5 Real-time Voice Conversation Teacher Plan

## Concept

V5 is intended to provide a voice-first AI conversation teacher where the learner speaks and hears spoken AI replies.

## Difference from ChatGPT Voice

The concept is similar to ChatGPT voice in that the learner can talk with AI, receive spoken replies, and continue a voice conversation.

However, current Phase 2 planning recommends a simpler first version before attempting fully interruptible realtime speech.

## Recommended First Version

Planned behavior:

```text
V5A Turn-Based Voice Conversation Teacher
User speaks
-> audio uploaded
-> Deepgram transcribes
-> AI generates reply
-> TTS creates audio
-> frontend plays AI reply
-> repeat until session ends
```

This is the recommended first implementation, not a currently implemented feature.

## Backend Requirements

Planned backend needs:

- speech-to-text integration
- AI reply generation
- text-to-speech generation
- turn persistence
- session lifecycle controls

## Frontend Requirements

Planned frontend needs:

- audio recording controls
- upload flow per turn
- playback of AI reply audio
- visible transcript history
- end-session control

Planned route:

```text
/voice-conversation
```

## Database Models

Planned models:

```text
VoiceConversationSession
VoiceConversationTurn
```

These models do not exist in the current repo yet.

## API Endpoints

Planned endpoints:

```text
POST /api/voice-conversation/sessions/start/
GET  /api/voice-conversation/sessions/<id>/
POST /api/voice-conversation/sessions/<id>/turns/
POST /api/voice-conversation/sessions/<id>/end/
GET  /api/voice-conversation/sessions/
```

## Practice-Only Rule

```text
V5 Voice Conversation Teacher is practice only.
It must not update SkillMastery.
It may read SkillMastery to personalize difficulty.
```

## Future Realtime Upgrade

Planned later upgrade:

```text
V5B Realtime / Interruptible Voice Conversation
```

Possible technical directions:

```text
WebSocket
WebRTC
Realtime speech API
```

## Navbar Placement

Target behavior:

```text
Teacher Sessions ▼
  Speaking Teacher
  Listening Teacher
  Pronunciation Teacher
  Voice Conversation
```

This navbar entry is planned only. It is not present in the current `Frontend/src/components/Header.tsx`.
