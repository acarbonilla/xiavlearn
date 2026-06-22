# XiAvLearn Phase 2 Documentation

## Phase 2 Summary

Phase 2 focused on stabilizing the learner flow after the MVP foundation. The main work areas were navigation cleanup, voice teacher sessions, voice diagnostic upgrades, official mastery separation, voice diagnostic history/reporting, and preparation for a future V5 voice conversation teacher.

## Completed Features

- Navigation cleanup with grouped dropdowns in `Frontend/src/components/Header.tsx`.
- Dedicated voice teacher session routes for speaking, listening, and pronunciation.
- Multi-step voice diagnostic flow in `Frontend/src/app/voice-diagnostic/page.tsx`.
- Multi-item voice diagnostic scoring and persistence in `Backend/agents/voice_services.py`.
- Voice diagnostic history using `VoiceDiagnosticSession` and `VoiceDiagnosticItem` in `Backend/agents/models.py`.
- Final voice diagnostic report endpoint and UI.
- Recommendation and study plan refresh behavior based on official voice mastery.
- Explicit separation between official mastery and practice-only teacher sessions.

## Architecture Decisions

- `SkillMastery` is the official mastery snapshot and must drive recommendation, study plan, and dashboard displays.
- Voice teacher sessions are practice only and must not write official mastery.
- Voice diagnostic writes official mastery only from final aggregate diagnostic results, not from per-item previews.
- Voice skills route directly to voice teacher session pages instead of requiring text modules.
- CEFR progression still depends on Grammar, Vocabulary, Listening, and Speaking. Pronunciation can be recommended without blocking progression.

## Current Product Flow

```text
Diagnostic
-> Official SkillMastery update
-> Recommendation
-> Study Plan
-> Teacher Session practice
-> Retake Diagnostic
-> CEFR progress
```

## Current Voice Flow

```text
Voice Diagnostic
-> Updates Pronunciation, Listening, Speaking SkillMastery
-> Shows Voice Diagnostic Report
-> Recommends matching Voice Teacher Session
-> User practices
-> User retakes Voice Diagnostic later
```

## Important Rules

- Dashboard must read official `SkillMastery`.
- Recommendation must read official `SkillMastery`.
- Study Plan must use official `SkillMastery` or recommendation derived from it.
- Teacher sessions must remain practice only.
- Practice results should be stored in session/turn records, not in `SkillMastery`.

## Next Major Feature

The next major planned feature is a V5 voice conversation teacher. Current code does not implement `voice-conversation` models, routes, or frontend pages yet. The Phase 2 plan for that feature is documented in [05_v5_voice_conversation_plan.md](/abs/path/C:/Users/dc/PycharmProjects/xiavlearn/Phase2_Documentation/05_v5_voice_conversation_plan.md).
