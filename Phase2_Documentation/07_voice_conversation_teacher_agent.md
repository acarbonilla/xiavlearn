# Voice Conversation Teacher Agent

## Purpose

The Voice Conversation Teacher Agent supports practice-only English speaking conversations. It should help the learner keep speaking, answer learner questions, give useful coaching, and guide the conversation into practical topics.

This feature is not an official assessment path.

## Practice-Only Rule

Voice Conversation must not:

- Update `SkillMastery`.
- Update diagnostic results.
- Unlock CEFR levels.
- Modify recommendation mastery.
- Modify study plan mastery.
- Produce official assessment scores.

Voice Conversation turns may be saved as practice session records only.

## Response Pipeline

```text
Learner transcript
-> generate_voice_conversation_response()
-> voice_conversation_response_prompt()
-> call_llm_json()
-> LLM JSON response, if configured and valid
-> response normalization
-> deterministic fallback, if LLM is disabled, misconfigured, fails, or returns invalid output
-> VoiceConversationTurn.ai_response_text
-> frontend conversation display and optional TTS
```

Realtime and turn-based Voice Conversation share the same teacher response generator.

## LLM Runtime Configuration

LLM settings are loaded through Django settings from environment configuration:

- `USE_LLM_AGENTS`
- `LLM_PROVIDER`
- `LLM_API_KEY`
- `LLM_MODEL`

`call_llm_json()` uses Django settings instead of reading only process environment variables. This allows values from backend `.env` loading to be available at runtime.

The LLM diagnostic helper reports only safe configuration state:

- Whether LLM agents are enabled.
- Whether provider is configured.
- Whether model is configured.
- Whether an API key is present.

It must not print or return secret values.

## LLM Skip Logging

When the LLM path is skipped, logs use this safe format:

```text
VOICE_LLM_SKIPPED reason=<reason> missing=<missing_config_names>
```

Examples:

```text
VOICE_LLM_SKIPPED reason=disabled missing=none
VOICE_LLM_SKIPPED reason=missing_config missing=LLM_API_KEY,LLM_MODEL
```

## Prompt Behavior

The current Teacher Agent prompt prioritizes conversation coaching over correction.

Response priority:

1. Understand learner intent.
2. If the learner asks a question, answer it briefly first.
3. Give one correction or natural rephrase only when there is a clear grammar, vocabulary, word order, or naturalness issue.
4. If no correction is needed, say the sentence is clear or natural.
5. Give one useful learning point, vocabulary tip, or speaking strategy.
6. Guide the learner into a practical conversation topic.
7. Ask exactly one specific follow-up question.

The teacher should not respond with correction only.

## Topic Guidance

The teacher is responsible for leading the practice conversation. If no clear topic exists, it should choose a practical beginner-friendly topic, such as:

- Work
- Daily life
- Family
- Hobbies
- Travel
- Technology
- Education
- Future goals

Once a topic is started, the teacher should stay on that topic for several turns unless the learner clearly changes topic.

## Correction Rules

Corrections are optional and should be used only when helpful.

Do:

- Correct one important issue only.
- Explain the correction briefly.
- Use varied wording such as `A small correction is`, `A clearer version is`, `You can also say`, or `This sounds more natural`.
- Use complete quotation marks around corrected sentences.

Do not:

- Present the learner's same sentence as a correction.
- Overuse `A more natural way to say it is`.
- Let correction replace answering the learner's question.
- Ask multiple follow-up questions.

## Deterministic Fallback

The deterministic fallback remains available for resilience when the LLM path is unavailable.

Fallback behavior should:

- Keep responses practice-only.
- Use recent conversation history when available.
- Avoid repeating a previous teacher question that the learner already answered.
- Use transcript keywords to choose a relevant follow-up question.
- Keep the response voice-friendly.
- Ask exactly one follow-up question.

Important keyword examples:

- Speaking: ask when the learner needs to use spoken English.
- Work or job: ask when the learner uses English at work.
- Technical support or customer: ask what customer problem the learner usually handles.
- Interview: ask what interview question the learner wants to answer better.
- Travel: ask where the learner would like to use English while traveling.
- Unclear response: ask the learner to try again with one short sentence.

## Expected Examples

### Clear Sentence, No Correction

Learner:

```text
AI helps me improve my speaking skills the most.
```

Expected style:

```text
Great answer. Your sentence is clear and natural. A useful speaking strategy is to add one real example from your life. What speaking situation do you practice most with AI?
```

### Advice Question

Learner:

```text
How can I speak a little every day if I don't live in an English-speaking country?
```

Expected style:

```text
Good question. You can speak a little every day by describing your routine, shadowing short videos, or recording yourself for one minute. Let's practice with daily life. What did you do today?
```

### Correction Needed

Learner:

```text
I usually listen to English learning podcast.
```

Expected style:

```text
Good answer. A small correction is: I usually listen to English learning podcasts. Use the plural podcasts when speaking generally. What podcast topic do you enjoy most?
```

## Validation Checklist

- Start a Voice Conversation session.
- Send a typed transcript.
- Confirm `metadata.practice_only` remains true.
- Confirm `metadata.response_mode` is `llm` when LLM config is enabled and the request succeeds.
- Confirm `metadata.response_mode` is `deterministic_fallback` when LLM is unavailable.
- Confirm fallback output is not repetitive generic text.
- Confirm the teacher answers learner questions before correcting.
- Confirm the teacher does not correct already natural sentences.
- Confirm the teacher asks exactly one follow-up question.
- Confirm no `SkillMastery`, diagnostic, CEFR progression, recommendation, or study plan data changes.
