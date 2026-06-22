# SkillMastery Rules and Data Separation

## Official Mastery

`SkillMastery` is the official current mastery snapshot per user and skill.

Current readers:

```text
Dashboard must read SkillMastery.
Recommendation must read SkillMastery.
Study Plan must use SkillMastery or Recommendation derived from SkillMastery.
```

Confirmed reader paths include:

- `Backend/learning/views.py`
- `Backend/agents/services.py`
- `Frontend/src/app/dashboard/page.tsx`
- `Frontend/src/app/recommendation/page.tsx`
- `Frontend/src/app/study-plan/page.tsx`

## Practice Scores

Practice scores are learner support data, not official mastery.

Practice data should go to:

```text
StudySession
LessonSession
LessonTurn
VoiceConversationSession
VoiceConversationTurn
```

Note:

- The first three are implemented now.
- `VoiceConversationSession` and `VoiceConversationTurn` are planned for V5 and do not exist in the current repo yet.

## Allowed SkillMastery Writers

Confirmed current writer categories:

```text
Text Diagnostic -> Grammar and Vocabulary SkillMastery
Pronunciation Diagnostic -> Pronunciation SkillMastery
Listening Diagnostic -> Listening SkillMastery
Speaking Diagnostic -> Speaking SkillMastery
Voice Diagnostic aggregate results -> voice SkillMastery
```

Current production write sites confirmed in code:

- `Backend/agents/services.py`
- `Backend/agents/voice_services.py`

## Forbidden SkillMastery Writers

These must not write official mastery:

```text
Speaking Teacher Session
Listening Teacher Session
Pronunciation Teacher Session
Text Teacher Session
Study Plan
Recommendation
Dashboard
V5 Voice Conversation Teacher
```

## Dashboard Rule

```text
Dashboard reads official SkillMastery and must not treat practice results as official mastery.
```

Current dashboard behavior is implemented in `Backend/learning/views.py` and rendered in `Frontend/src/app/dashboard/page.tsx`.

## Recommendation Rule

```text
Recommendation reads latest official SkillMastery.
Voice skills can be recommended when officially weak.
```

Current recommendation logic is implemented in `Backend/agents/services.py`.

## Study Plan Rule

```text
Study Plan uses official SkillMastery-derived focus.
Voice skills route to voice teacher session pages.
```

Current direct voice routes:

```text
Pronunciation -> /pronunciation-teacher
Listening -> /listening-teacher
Speaking -> /speaking-teacher
```

## CEFR Progression Rule

```text
Grammar, Vocabulary, Listening, and Speaking are core progression skills.
All core skills must reach the required threshold before level progression.
Pronunciation can be recommended if weak, but it should not block CEFR progression unless product rules change later.
```

This rule is reflected in current tests and learner messaging.
