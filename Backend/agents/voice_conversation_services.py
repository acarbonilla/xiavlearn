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
TOPIC_FOLLOW_UPS = (
    ('yesterday', 'What happened after that?'),
    ('today', 'What is the next step for you today?'),
    ('work', 'Can you describe one specific example from work?'),
    ('job', 'What part of your job would you like to explain more?'),
    ('school', 'What happened in that situation at school?'),
    ('english', 'What part of learning English do you want to improve next?'),
    ('practice', 'What would you like to practice next?'),
    ('family', 'Can you tell me one more detail about your family?'),
    ('friend', 'What can you say about that friend?'),
)
SKILL_BASED_TIPS = {
    VoiceConversationSession.TARGET_SKILL_SPEAKING: (
        'Try adding one reason or one example in your next answer.'
    ),
    VoiceConversationSession.TARGET_SKILL_LISTENING: (
        'Focus on one key detail first, then add a short supporting detail.'
    ),
    VoiceConversationSession.TARGET_SKILL_PRONUNCIATION: (
        'Keep your next sentence short and clear so it will be easier to say aloud later.'
    ),
    VoiceConversationSession.TARGET_SKILL_GENERAL: (
        'Keep your ideas organized in one or two clear sentences.'
    ),
}
SKILL_BASED_FOLLOW_UPS = {
    VoiceConversationSession.TARGET_SKILL_SPEAKING: (
        'Can you say one more sentence about that?'
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


def _normalize_user_transcript(user_transcript):
    if not isinstance(user_transcript, str):
        raise ValueError('user_transcript must be a non-empty string.')
    normalized = re.sub(r'\s+', ' ', user_transcript).strip()
    if not normalized:
        raise ValueError('user_transcript must be a non-empty string.')
    return normalized


def _count_words(text):
    return len(re.findall(r"[A-Za-z']+", text))


def _build_response_opening(word_count):
    if word_count < VOICE_CONVERSATION_SHORT_RESPONSE_THRESHOLD:
        return 'Thanks for answering. Please try to use a longer sentence next time.'
    if word_count < VOICE_CONVERSATION_DETAILED_RESPONSE_THRESHOLD:
        return 'Good start. Your answer is understandable and connected.'
    return 'Nice work. Your answer includes clear detail and supports the conversation.'


def _build_skill_tip(target_skill):
    return SKILL_BASED_TIPS.get(
        target_skill,
        SKILL_BASED_TIPS[VoiceConversationSession.TARGET_SKILL_GENERAL],
    )


def _build_follow_up_question(session, normalized_transcript):
    lowered = normalized_transcript.lower()
    for keyword, question in TOPIC_FOLLOW_UPS:
        if keyword in lowered:
            return question
    return SKILL_BASED_FOLLOW_UPS.get(
        session.target_skill,
        SKILL_BASED_FOLLOW_UPS[VoiceConversationSession.TARGET_SKILL_GENERAL],
    )


def build_voice_conversation_fallback_response(session, user_transcript):
    normalized_transcript = _normalize_user_transcript(user_transcript)
    word_count = _count_words(normalized_transcript)
    opening = _build_response_opening(word_count)
    tip = _build_skill_tip(session.target_skill)
    follow_up = _build_follow_up_question(session, normalized_transcript)
    return (
        f'{PRACTICE_ONLY_LABEL} {opening} {tip} '
        f'Teacher follow-up: {follow_up}'
    )


def _normalize_ai_response_text(response_text):
    if not isinstance(response_text, str):
        return None
    normalized = re.sub(r'\s+', ' ', response_text).strip()
    if not normalized:
        return None
    if not normalized.startswith(PRACTICE_ONLY_LABEL):
        normalized = f'{PRACTICE_ONLY_LABEL} {normalized}'
    if 'Teacher follow-up:' not in normalized:
        normalized = f'{normalized} Teacher follow-up: What would you like to add next?'
    return normalized


def generate_voice_conversation_response(session, user_transcript):
    normalized_transcript = _normalize_user_transcript(user_transcript)
    llm_payload = call_llm_json(
        *voice_conversation_response_prompt(session, normalized_transcript)
    )
    if isinstance(llm_payload, dict):
        normalized_response = _normalize_ai_response_text(
            llm_payload.get('response_text')
        )
        if normalized_response:
            return normalized_response, 'llm'

    return (
        build_voice_conversation_fallback_response(session, normalized_transcript),
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
