import re

from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from .llm_client import call_llm_json
from .models import VoiceConversationSession, VoiceConversationTurn
from .prompts import voice_conversation_response_prompt
from .voice_services import VoiceDiagnosticConfigError, VoiceDiagnosticError, synthesize_tts
from .voice_services import transcribe_audio


PRACTICE_ONLY_LABEL = 'Practice feedback only:'
VOICE_CONVERSATION_TURN_CREATE_MAX_RETRIES = 3
VOICE_CONVERSATION_SHORT_RESPONSE_THRESHOLD = 5
VOICE_CONVERSATION_DETAILED_RESPONSE_THRESHOLD = 12
SUPPORTED_CEFR_LEVELS = {'A1', 'A2', 'B1', 'B2', 'C1', 'C2'}
TOPIC_FOLLOW_UPS = (
    ('technical support', 'What kind of customer problem do you usually handle?'),
    ('customer', 'What kind of customer problem do you usually handle?'),
    ('interview', 'What interview question do you want to answer clearly?'),
    ('travel', 'Where would you like to use English when traveling?'),
    ('study', 'What subject do you study in English?'),
    ('yesterday', 'What happened after that?'),
    ('today', 'What is the next step for you today?'),
    ('work', 'What part of your job do you want to explain in English?'),
    ('job', 'Why is speaking important in your job?'),
    ('school', 'What happened in that situation at school?'),
    ('english', 'Which English situation do you want to practice first?'),
    ('practice', 'What would you like to practice next?'),
    ('family', 'Can you tell me one more detail about your family?'),
    ('friend', 'What can you say about that friend?'),
)
CEFR_ENCOURAGEMENT = {
    'A1': 'Good try. I understood your idea.',
    'A2': 'Good answer. I understood your idea.',
    'B1': 'Good answer. Your idea is clear.',
    'B2': 'Good response. You gave a clear idea.',
    'C1': 'Strong response. Your meaning is clear.',
    'C2': 'Strong response. Your meaning is precise.',
}
SKILL_BASED_FOLLOW_UPS = {
    VoiceConversationSession.TARGET_SKILL_SPEAKING: (
        'When do you need to use spoken English?'
    ),
    VoiceConversationSession.TARGET_SKILL_LISTENING: (
        'What is the main detail you want to highlight?'
    ),
    VoiceConversationSession.TARGET_SKILL_PRONUNCIATION: (
        'Can you repeat the same idea with one short, clear sentence?'
    ),
    VoiceConversationSession.TARGET_SKILL_GENERAL: (
        'What would you like to add next?'
    ),
}
UNCLEAR_RESPONSES = {'um', 'uh', 'hmm', 'mmm', 'er', 'ah'}
ROBOTIC_LABEL_PATTERNS = (
    r'\bPractice feedback only:\s*',
    r'\bCorrection:\s*',
    r'\bLearning point:\s*',
    r'\bTeacher follow-up:\s*',
)


def _normalize_user_transcript(user_transcript):
    if not isinstance(user_transcript, str):
        raise ValueError('user_transcript must be a non-empty string.')
    normalized = re.sub(r'\s+', ' ', user_transcript).strip()
    if not normalized:
        raise ValueError('user_transcript must be a non-empty string.')
    return normalized


def _count_words(text):
    return len(re.findall(r"[A-Za-z']+", text))


def _normalized_cefr_level(session):
    normalized = (getattr(session, 'cefr_level', '') or '').strip().upper()
    if normalized in SUPPORTED_CEFR_LEVELS:
        return normalized
    return 'A2'


def _first_sentence(text):
    sentence = re.split(r'[.!?]', text, maxsplit=1)[0].strip(' ,')
    return sentence or text


def _simple_sentence_from_transcript(normalized_transcript):
    sentence = _first_sentence(normalized_transcript)
    if not sentence:
        return 'I need a little more time to answer.'
    sentence = sentence[0].upper() + sentence[1:]
    if not sentence.endswith('.'):
        sentence = f'{sentence}.'
    return sentence


def _normalize_question_text(question):
    return re.sub(r'[^a-z0-9]+', ' ', (question or '').lower()).strip()


def _last_question(text):
    if not text:
        return ''
    matches = re.findall(r'([^?]*\?)', text)
    if not matches:
        return ''
    return re.sub(r'\s+', ' ', matches[-1]).strip()


def _recent_conversation_turns(session, limit=5):
    turns_manager = getattr(session, 'turns', None)
    if turns_manager is None:
        return []
    try:
        turns = list(turns_manager.order_by('-turn_number')[:limit])
    except Exception:
        return []
    turns.reverse()
    return [
        {
            'learner': turn.user_transcript,
            'teacher': turn.ai_response_text,
        }
        for turn in turns
    ]


def _previous_teacher_question(recent_turns):
    if not recent_turns:
        return ''
    for turn in reversed(recent_turns):
        question = _last_question(turn.get('teacher', ''))
        if question:
            return question
    return ''


def _learner_answered_reason_question(previous_question, normalized_transcript):
    question = _normalize_question_text(previous_question)
    answer = normalized_transcript.lower()
    if 'reason' not in question:
        return False
    return bool(
        'reason' in answer
        or 'because' in answer
        or 'so i can' in answer
        or 'to improve' in answer
        or 'want to improve' in answer
    )


def _speaking_context_follow_up(normalized_transcript):
    lowered = normalized_transcript.lower()
    if 'work' in lowered or 'job' in lowered:
        return 'When do you usually use English at work?'
    if 'customer' in lowered or 'support' in lowered:
        return 'Do you want to improve speaking for meetings, interviews, or customer support?'
    return 'When do you need to use spoken English?'


def _build_follow_up_question(
    session,
    normalized_transcript,
    cefr_level,
    recent_turns=None,
):
    lowered = normalized_transcript.lower()
    previous_question = _previous_teacher_question(recent_turns)
    if _learner_answered_reason_question(previous_question, normalized_transcript):
        return _speaking_context_follow_up(normalized_transcript)
    if 'speaking' in lowered or 'speak' in lowered:
        return _speaking_context_follow_up(normalized_transcript)
    if cefr_level == 'A1':
        if 'technical support' in lowered or 'customer' in lowered:
            return 'What customer problem do you fix?'
        if 'work' in lowered or 'job' in lowered:
            return 'What is your job?'
        if 'english' in lowered:
            return 'What English word do you want to practice?'
    for keyword, question in TOPIC_FOLLOW_UPS:
        if keyword in lowered:
            return question
    return SKILL_BASED_FOLLOW_UPS.get(
        session.target_skill,
        SKILL_BASED_FOLLOW_UPS[VoiceConversationSession.TARGET_SKILL_GENERAL],
    )


def _is_unclear_response(normalized_transcript):
    words = re.findall(r"[A-Za-z']+", normalized_transcript.lower())
    if not words:
        return True
    return len(words) <= 2 and all(word in UNCLEAR_RESPONSES for word in words)


def _build_rephrase_and_learning_point(normalized_transcript, cefr_level):
    lowered = normalized_transcript.lower()
    if _is_unclear_response(normalized_transcript):
        return None, 'Try one short sentence with a clear idea.'
    if re.search(r'\bthe\s+reason\s+is\s+to\s+improve\b', lowered):
        return (
            'I want to improve my speaking skills.',
            "English speakers often use a direct sentence instead of saying 'The reason is.'",
        )
    if 'technical support' in lowered:
        if re.search(r'\bi\s+work\s+technical\s+support\b', lowered):
            return (
                'I work in technical support, and I help customers.',
                "Use 'work in' for a field or department.",
            )
        if re.search(r'\bi\s+work\s+in\s+technical\s+support\b', lowered):
            return (
                'I work in technical support and help customers solve problems.',
                'Add a specific action after your job field.',
            )
        return (
            'I help customers solve technical support problems.',
            'Use specific verbs like help, solve, or explain.',
        )
    if re.search(r'\bi\s+want\s+improve\b', lowered):
        if 'because my job' in lowered:
            return (
                'I want to improve my speaking because of my job.',
                "Use 'want to' before a verb.",
            )
        return (
            re.sub(
                r'\bI want improve\b',
                'I want to improve',
                _simple_sentence_from_transcript(normalized_transcript),
                flags=re.IGNORECASE,
            ),
            "Use 'want to' before a verb.",
        )
    if 'because my job' in lowered:
        return (
            'This is important because of my job.',
            "Use 'because of' before a noun.",
        )
    if re.search(r'\bhelp customer\b', lowered):
        return (
            'I help customers.',
            "Use the plural 'customers' when speaking generally.",
        )
    if re.search(r'\bi\s+am\s+work\b', lowered):
        return (
            'I work every day.',
            "Use 'I work' for your job or regular activity.",
        )
    if re.search(r'\bi\s+no\s+understand\b', lowered):
        return (
            'I do not understand.',
            "Use 'do not' before the main verb in a negative sentence.",
        )
    if cefr_level == 'A1':
        return (
            _simple_sentence_from_transcript(normalized_transcript),
            'Use one short, complete sentence.',
        )
    if cefr_level == 'A2':
        return (
            _simple_sentence_from_transcript(normalized_transcript),
            'Keep the sentence direct and easy to say aloud.',
        )
    if cefr_level in {'B1', 'B2'}:
        return (
            _simple_sentence_from_transcript(normalized_transcript),
            'Connect your idea with one clear reason or example.',
        )
    return (
        _simple_sentence_from_transcript(normalized_transcript),
        'Choose precise wording so your idea sounds natural and specific.',
    )


def _build_fallback_encouragement(cefr_level, word_count):
    if word_count < VOICE_CONVERSATION_SHORT_RESPONSE_THRESHOLD:
        return 'Good try. I understood part of your idea.'
    if word_count >= VOICE_CONVERSATION_DETAILED_RESPONSE_THRESHOLD and cefr_level in {'B2', 'C1', 'C2'}:
        return CEFR_ENCOURAGEMENT[cefr_level]
    return CEFR_ENCOURAGEMENT.get(cefr_level, CEFR_ENCOURAGEMENT['A2'])


def _trim_to_one_question(response_text):
    first_question_index = response_text.find('?')
    if first_question_index == -1:
        return response_text
    second_question_index = response_text.find('?', first_question_index + 1)
    if second_question_index == -1:
        return response_text
    return response_text[:first_question_index + 1].strip()


def _strip_robotic_labels(response_text):
    normalized = response_text
    for pattern in ROBOTIC_LABEL_PATTERNS:
        normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', normalized).strip()


def _avoid_repeated_question(question, session, normalized_transcript, recent_turns=None):
    previous_question = _previous_teacher_question(recent_turns)
    if not previous_question:
        return question
    previous_normalized = _normalize_question_text(previous_question)
    current_normalized = _normalize_question_text(question)
    if current_normalized and current_normalized != previous_normalized:
        return question
    if 'speaking' in normalized_transcript.lower() or 'reason' in normalized_transcript.lower():
        return _speaking_context_follow_up(normalized_transcript)
    if 'technical support' in normalized_transcript.lower() or 'customer' in normalized_transcript.lower():
        return 'What kind of customer problem do you usually handle?'
    return 'What detail can you add next?'


def _contextual_follow_up(session=None, user_transcript=None, recent_turns=None):
    if session is not None and user_transcript:
        question = _build_follow_up_question(
            session,
            user_transcript,
            _normalized_cefr_level(session),
            recent_turns=recent_turns,
        )
        return _avoid_repeated_question(
            question,
            session,
            user_transcript,
            recent_turns=recent_turns,
        )
    return 'What would you like to add next?'


def build_voice_conversation_fallback_response(
    session,
    user_transcript,
    recent_turns=None,
):
    normalized_transcript = _normalize_user_transcript(user_transcript)
    recent_turns = recent_turns if recent_turns is not None else _recent_conversation_turns(session)
    cefr_level = _normalized_cefr_level(session)
    word_count = _count_words(normalized_transcript)
    encouragement = _build_fallback_encouragement(cefr_level, word_count)
    rephrase, learning_point = _build_rephrase_and_learning_point(
        normalized_transcript,
        cefr_level,
    )
    follow_up = _contextual_follow_up(
        session,
        normalized_transcript,
        recent_turns=recent_turns,
    )
    if _is_unclear_response(normalized_transcript):
        response_text = (
            f'{encouragement} Please try one short sentence. '
            f'{learning_point} Can you try again with one short sentence?'
        )
        return _trim_to_one_question(response_text)
    correction_label = 'A better sentence is'
    if cefr_level in {'B2', 'C1', 'C2'}:
        correction_label = 'A more natural version is'
    response_text = (
        f'{encouragement} '
        f'{correction_label}: {rephrase} '
        f'{learning_point} '
        f'{follow_up}'
    )
    return _trim_to_one_question(response_text)


def _normalize_ai_response_text(
    response_text,
    session=None,
    user_transcript=None,
    recent_turns=None,
    strip_labels=False,
):
    if not isinstance(response_text, str):
        return None
    normalized = re.sub(r'\s+', ' ', response_text).strip()
    if not normalized:
        return None
    if strip_labels:
        normalized = _strip_robotic_labels(normalized)
    if '?' not in normalized:
        normalized = (
            f'{normalized} '
            f'{_contextual_follow_up(session, user_transcript, recent_turns=recent_turns)}'
        )
    return _trim_to_one_question(normalized)


def generate_voice_conversation_response(session, user_transcript):
    normalized_transcript = _normalize_user_transcript(user_transcript)
    recent_turns = _recent_conversation_turns(session)
    llm_payload = call_llm_json(
        *voice_conversation_response_prompt(
            session,
            normalized_transcript,
            recent_turns=recent_turns,
        )
    )
    if isinstance(llm_payload, dict):
        normalized_response = _normalize_ai_response_text(
            llm_payload.get('response_text'),
            session=session,
            user_transcript=normalized_transcript,
            recent_turns=recent_turns,
            strip_labels=True,
        )
        if normalized_response:
            return normalized_response, 'llm'

    return (
        build_voice_conversation_fallback_response(
            session,
            normalized_transcript,
            recent_turns=recent_turns,
        ),
        'deterministic_fallback',
    )


def _tts_file_extension(content_type):
    if content_type == 'audio/wav':
        return 'wav'
    if content_type == 'audio/ogg':
        return 'ogg'
    return 'mp3'


def _tts_file_name(turn, content_type):
    extension = _tts_file_extension(content_type)
    return f'session-{turn.session_id}-turn-{turn.turn_number}.{extension}'


def _attach_ai_audio_content(turn, audio_content, content_type):
    turn.ai_audio.save(
        _tts_file_name(turn, content_type),
        ContentFile(audio_content),
        save=False,
    )
    return content_type


def _attach_ai_audio(turn):
    audio_content, content_type = synthesize_tts(turn.ai_response_text)
    return _attach_ai_audio_content(turn, audio_content, content_type)


def _next_voice_conversation_turn_number(session):
    return (
        session.turns.aggregate(max_turn_number=Max('turn_number'))['max_turn_number'] or 0
    ) + 1


def _create_turn_with_retry(*, session, create_kwargs):
    last_error = None
    for _ in range(VOICE_CONVERSATION_TURN_CREATE_MAX_RETRIES):
        try:
            with transaction.atomic():
                VoiceConversationSession.objects.select_for_update().filter(
                    pk=session.pk
                ).exists()
                return VoiceConversationTurn.objects.create(
                    session=session,
                    turn_number=_next_voice_conversation_turn_number(session),
                    **create_kwargs,
                )
        except IntegrityError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise IntegrityError('Voice conversation turn creation failed.')


@transaction.atomic
def create_voice_conversation_turn(
    *,
    session,
    user_transcript=None,
    user,
    user_audio=None,
    transcript_source=VoiceConversationTurn.TRANSCRIPT_SOURCE_FALLBACK,
    metadata=None,
):
    if session.user_id != user.id:
        raise VoiceConversationSession.DoesNotExist
    if session.status != VoiceConversationSession.STATUS_ACTIVE:
        raise ValueError('Only active voice conversation sessions can accept new turns.')

    input_mode = 'manual_transcript'
    turn_metadata = dict(metadata or {})
    if user_audio is not None:
        transcript_source = VoiceConversationTurn.TRANSCRIPT_SOURCE_DEEPGRAM
        normalized_transcript = _normalize_user_transcript(transcribe_audio(user_audio))
        user_audio.seek(0)
        input_mode = 'audio_upload'
        turn_metadata.update(
            {
                'audio_uploaded': True,
                'transcription_provider': 'deepgram',
            }
        )
    else:
        normalized_transcript = _normalize_user_transcript(user_transcript)

    ai_response_text, response_source = generate_voice_conversation_response(
        session,
        normalized_transcript,
    )
    turn_metadata.update(
        {
            'practice_only': True,
            'word_count': _count_words(normalized_transcript),
            'response_mode': response_source,
            'input_mode': input_mode,
        }
    )
    turn = _create_turn_with_retry(
        session=session,
        create_kwargs={
            'user_transcript': normalized_transcript,
            'user_audio': user_audio,
            'transcript_source': transcript_source,
            'metadata': turn_metadata,
            'ai_response_text': ai_response_text,
        },
    )
    try:
        content_type = _attach_ai_audio(turn)
    except (VoiceDiagnosticConfigError, VoiceDiagnosticError) as exc:
        turn_metadata['tts_generated'] = False
        turn_metadata['tts_error'] = str(exc)
    else:
        turn_metadata['tts_generated'] = True
        turn_metadata['tts_provider'] = 'deepgram'
        turn_metadata['tts_content_type'] = content_type

    turn.metadata = turn_metadata
    update_fields = ['metadata']
    if turn.ai_audio:
        update_fields.append('ai_audio')
    turn.save(update_fields=update_fields)
    return turn


@transaction.atomic
def create_realtime_voice_conversation_turn(
    *,
    session,
    user,
    user_transcript,
    ai_response_text,
    response_id,
    response_source,
    stt_provider='deepgram',
    ai_provider=None,
    tts_provider=None,
    ai_audio_content=None,
    ai_audio_content_type=None,
    interrupted=False,
    fallback_used=False,
    metadata=None,
):
    if session.user_id != user.id:
        raise VoiceConversationSession.DoesNotExist
    if session.status != VoiceConversationSession.STATUS_ACTIVE:
        raise ValueError('Only active voice conversation sessions can accept new turns.')

    normalized_transcript = _normalize_user_transcript(user_transcript)
    normalized_ai_response = _normalize_ai_response_text(ai_response_text)
    if not normalized_ai_response:
        raise ValueError('ai_response_text must be a non-empty string.')

    turn_metadata = dict(metadata or {})
    turn_metadata.update(
        {
            'practice_only': True,
            'mode': 'realtime',
            'service_version': 'v5b-7',
            'response_id': response_id,
            'stt_provider': stt_provider,
            'ai_provider': ai_provider or response_source,
            'response_mode': response_source,
            'fallback_used': bool(fallback_used),
            'interrupted': bool(interrupted),
            'word_count': _count_words(normalized_transcript),
            'input_mode': 'realtime_streaming',
        }
    )
    if tts_provider:
        turn_metadata['tts_provider'] = tts_provider
    turn_metadata.setdefault('realtime_persisted_at', timezone.now().isoformat())

    turn = _create_turn_with_retry(
        session=session,
        create_kwargs={
            'user_transcript': normalized_transcript,
            'ai_response_text': normalized_ai_response,
            'transcript_source': VoiceConversationTurn.TRANSCRIPT_SOURCE_DEEPGRAM_STREAMING,
            'metadata': turn_metadata,
        },
    )

    if ai_audio_content is not None and ai_audio_content_type:
        _attach_ai_audio_content(turn, ai_audio_content, ai_audio_content_type)
        turn_metadata['tts_generated'] = True
        turn_metadata['tts_content_type'] = ai_audio_content_type
    else:
        turn_metadata.setdefault('tts_generated', False)

    turn.metadata = turn_metadata
    update_fields = ['metadata']
    if turn.ai_audio:
        update_fields.append('ai_audio')
    turn.save(update_fields=update_fields)
    return turn
