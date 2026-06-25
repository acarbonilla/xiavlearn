import base64
import binascii
import math

from django.utils import timezone


PROTOCOL_VERSION = 'v5b-7'
REALTIME_STAGE = 'persistence_fallback'
MAX_EVENT_ID_LENGTH = 100
MAX_STATUS_FIELDS = 12
MAX_STATUS_KEY_LENGTH = 64
MAX_STATUS_STRING_LENGTH = 256
MAX_CHUNK_ID_LENGTH = 100
MAX_MIME_TYPE_LENGTH = 100
MAX_CHUNK_SIZE_BYTES = 1024 * 1024
MAX_CHUNK_DURATION_MS = 30_000
MAX_BASE64_LENGTH = math.ceil(MAX_CHUNK_SIZE_BYTES / 3) * 4 + 4
MAX_INTERRUPT_SOURCE_LENGTH = 64
MAX_INTERRUPT_REASON_LENGTH = 256
MAX_RESPONSE_ID_LENGTH = 100


class RealtimeProtocolError(ValueError):
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(message)


def iso_timestamp():
    return timezone.now().isoformat().replace('+00:00', 'Z')


def build_connected_event(session_id):
    return {
        'type': 'connected',
        'session_id': session_id,
        'protocol_version': PROTOCOL_VERSION,
        'realtime_stage': REALTIME_STAGE,
        'transport': 'websocket',
        'message': 'Realtime voice conversation socket connected.',
    }


def build_session_status_event(session):
    return {
        'type': 'session_status',
        'protocol_version': PROTOCOL_VERSION,
        'session': {
            'id': session['id'],
            'status': session['status'],
            'target_skill': session['target_skill'],
            'cefr_level': session['cefr_level'],
            'turn_count': session['turn_count'],
            'practice_only': True,
            'realtime_stage': REALTIME_STAGE,
        },
    }


def build_pong_event(session_id, event_id=None, client_ts=None):
    event = {
        'type': 'pong',
        'session_id': session_id,
        'protocol_version': PROTOCOL_VERSION,
        'server_ts': iso_timestamp(),
    }
    if event_id is not None:
        event['event_id'] = event_id
    if client_ts is not None:
        event['client_ts'] = client_ts
    return event


def build_client_status_ack_event(session_id, event_id, status_payload):
    return {
        'type': 'client_status_ack',
        'session_id': session_id,
        'protocol_version': PROTOCOL_VERSION,
        'event_id': event_id,
        'accepted': True,
        'accepted_fields': sorted(status_payload.keys()),
        'server_ts': iso_timestamp(),
    }


def build_audio_chunk_ack_event(session_id, event_id, chunk_payload):
    return {
        'type': 'audio_chunk_ack',
        'session_id': session_id,
        'protocol_version': PROTOCOL_VERSION,
        'event_id': event_id,
        'chunk_id': chunk_payload['chunk_id'],
        'sequence': chunk_payload['sequence'],
        'size_bytes': chunk_payload['size_bytes'],
        'accepted': True,
        'ingest_stage': 'base64_validated',
        'server_ts': iso_timestamp(),
    }


def build_stt_status_event(session_id, *, state, provider, message):
    return {
        'type': 'stt_status',
        'session_id': session_id,
        'protocol_version': PROTOCOL_VERSION,
        'provider': provider,
        'state': state,
        'message': message,
        'server_ts': iso_timestamp(),
    }


def build_transcript_event(
    session_id,
    *,
    provider,
    transcript,
    is_final,
    speech_final,
    provider_event_type,
):
    event = {
        'type': 'transcript_final' if is_final else 'transcript_partial',
        'session_id': session_id,
        'protocol_version': PROTOCOL_VERSION,
        'provider': provider,
        'transcript': transcript,
        'is_final': is_final,
        'speech_final': speech_final,
        'provider_event_type': provider_event_type,
        'server_ts': iso_timestamp(),
    }
    return event


def build_ai_response_start_event(session_id, *, response_id, transcript):
    return {
        'type': 'ai_response_start',
        'session_id': session_id,
        'protocol_version': PROTOCOL_VERSION,
        'response_id': response_id,
        'practice_only': True,
        'transcript': transcript,
        'server_ts': iso_timestamp(),
    }


def build_ai_response_delta_event(
    session_id,
    *,
    response_id,
    sequence,
    delta_text,
    accumulated_text,
):
    return {
        'type': 'ai_response_delta',
        'session_id': session_id,
        'protocol_version': PROTOCOL_VERSION,
        'response_id': response_id,
        'sequence': sequence,
        'delta_text': delta_text,
        'accumulated_text': accumulated_text,
        'server_ts': iso_timestamp(),
    }


def build_ai_response_final_event(
    session_id,
    *,
    response_id,
    response_text,
    response_source,
    chunk_count,
):
    return {
        'type': 'ai_response_final',
        'session_id': session_id,
        'protocol_version': PROTOCOL_VERSION,
        'response_id': response_id,
        'practice_only': True,
        'response_text': response_text,
        'response_source': response_source,
        'chunk_count': chunk_count,
        'server_ts': iso_timestamp(),
    }


def build_ai_response_error_event(session_id, *, response_id, code, message):
    return {
        'type': 'ai_response_error',
        'session_id': session_id,
        'protocol_version': PROTOCOL_VERSION,
        'response_id': response_id,
        'code': code,
        'message': message,
        'server_ts': iso_timestamp(),
    }


def build_tts_start_event(
    session_id,
    *,
    response_id,
    provider,
    content_type,
    total_size_bytes,
    chunk_count,
):
    return {
        'type': 'tts_audio_start',
        'session_id': session_id,
        'protocol_version': PROTOCOL_VERSION,
        'response_id': response_id,
        'provider': provider,
        'content_type': content_type,
        'total_size_bytes': total_size_bytes,
        'chunk_count': chunk_count,
        'practice_only': True,
        'server_ts': iso_timestamp(),
    }


def build_tts_chunk_event(
    session_id,
    *,
    response_id,
    sequence,
    chunk_base64,
    size_bytes,
    is_final,
):
    return {
        'type': 'tts_audio_chunk',
        'session_id': session_id,
        'protocol_version': PROTOCOL_VERSION,
        'response_id': response_id,
        'sequence': sequence,
        'audio_base64': chunk_base64,
        'size_bytes': size_bytes,
        'is_final': is_final,
        'server_ts': iso_timestamp(),
    }


def build_tts_complete_event(
    session_id,
    *,
    response_id,
    provider,
    content_type,
    total_size_bytes,
    chunk_count,
):
    return {
        'type': 'tts_audio_complete',
        'session_id': session_id,
        'protocol_version': PROTOCOL_VERSION,
        'response_id': response_id,
        'provider': provider,
        'content_type': content_type,
        'total_size_bytes': total_size_bytes,
        'chunk_count': chunk_count,
        'practice_only': True,
        'server_ts': iso_timestamp(),
    }


def build_tts_error_event(session_id, *, response_id, code, message):
    return {
        'type': 'tts_audio_error',
        'session_id': session_id,
        'protocol_version': PROTOCOL_VERSION,
        'response_id': response_id,
        'code': code,
        'message': message,
        'server_ts': iso_timestamp(),
    }


def build_assistant_interrupted_event(
    session_id,
    *,
    response_id,
    trigger,
    reason,
    previous_state,
    had_active_response,
):
    return {
        'type': 'assistant_interrupted',
        'session_id': session_id,
        'protocol_version': PROTOCOL_VERSION,
        'response_id': response_id,
        'trigger': trigger,
        'reason': reason,
        'previous_state': previous_state,
        'had_active_response': had_active_response,
        'stop_playback': True,
        'practice_only': True,
        'server_ts': iso_timestamp(),
    }


def build_realtime_turn_persisted_event(session_id, *, response_id, turn):
    return {
        'type': 'realtime_turn_persisted',
        'session_id': session_id,
        'protocol_version': PROTOCOL_VERSION,
        'response_id': response_id,
        'turn': turn,
        'practice_only': True,
        'server_ts': iso_timestamp(),
    }


def build_realtime_turn_interrupted_event(session_id, *, response_id, turn):
    return {
        'type': 'realtime_turn_interrupted',
        'session_id': session_id,
        'protocol_version': PROTOCOL_VERSION,
        'response_id': response_id,
        'turn': turn,
        'practice_only': True,
        'server_ts': iso_timestamp(),
    }


def build_error_event(code, message, *, event_id=None, for_type=None):
    event = {
        'type': 'error',
        'code': code,
        'message': message,
        'protocol_version': PROTOCOL_VERSION,
    }
    if event_id is not None:
        event['event_id'] = event_id
    if for_type is not None:
        event['for_type'] = for_type
    return event


def validate_optional_event_id(value):
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise RealtimeProtocolError(
            'invalid_payload',
            'event_id must be a non-empty string when provided.',
        )
    normalized = value.strip()
    if len(normalized) > MAX_EVENT_ID_LENGTH:
        raise RealtimeProtocolError(
            'invalid_payload',
            'event_id is too long.',
        )
    return normalized


def parse_ping_event(content):
    event_id = validate_optional_event_id(content.get('event_id'))
    client_ts = content.get('client_ts')
    if client_ts is not None and not isinstance(client_ts, str):
        raise RealtimeProtocolError(
            'invalid_payload',
            'client_ts must be a string when provided.',
        )
    return {
        'event_id': event_id,
        'client_ts': client_ts,
    }


def sanitize_client_status_payload(status_payload):
    if not isinstance(status_payload, dict) or not status_payload:
        raise RealtimeProtocolError(
            'invalid_payload',
            'status must be a non-empty object.',
        )
    if len(status_payload) > MAX_STATUS_FIELDS:
        raise RealtimeProtocolError(
            'invalid_payload',
            'status has too many fields.',
        )

    sanitized = {}
    for key, value in status_payload.items():
        if not isinstance(key, str) or not key.strip():
            raise RealtimeProtocolError(
                'invalid_payload',
                'status keys must be non-empty strings.',
            )
        normalized_key = key.strip()
        if len(normalized_key) > MAX_STATUS_KEY_LENGTH:
            raise RealtimeProtocolError(
                'invalid_payload',
                'status key is too long.',
            )
        if isinstance(value, str):
            normalized_value = value.strip()
            if len(normalized_value) > MAX_STATUS_STRING_LENGTH:
                raise RealtimeProtocolError(
                    'invalid_payload',
                    f'status field "{normalized_key}" is too long.',
                )
            sanitized[normalized_key] = normalized_value
            continue
        if isinstance(value, (bool, int, float)) or value is None:
            sanitized[normalized_key] = value
            continue
        raise RealtimeProtocolError(
            'invalid_payload',
            f'status field "{normalized_key}" must be scalar JSON data.',
        )
    return sanitized


def parse_client_status_event(content):
    return {
        'event_id': validate_optional_event_id(content.get('event_id')),
        'status': sanitize_client_status_payload(content.get('status')),
    }


def parse_interrupt_event(content):
    event_id = validate_optional_event_id(content.get('event_id'))
    source = content.get('source') or 'manual_interrupt'
    reason = content.get('reason') or 'Learner interrupted the current AI output.'

    if not isinstance(source, str) or not source.strip():
        raise RealtimeProtocolError(
            'invalid_payload',
            'source must be a non-empty string.',
        )
    normalized_source = source.strip()
    if len(normalized_source) > MAX_INTERRUPT_SOURCE_LENGTH:
        raise RealtimeProtocolError(
            'invalid_payload',
            'source is too long.',
        )

    if not isinstance(reason, str) or not reason.strip():
        raise RealtimeProtocolError(
            'invalid_payload',
            'reason must be a non-empty string.',
        )
    normalized_reason = reason.strip()
    if len(normalized_reason) > MAX_INTERRUPT_REASON_LENGTH:
        raise RealtimeProtocolError(
            'invalid_payload',
            'reason is too long.',
        )

    return {
        'event_id': event_id,
        'source': normalized_source,
        'reason': normalized_reason,
    }


def parse_assistant_playback_complete_event(content):
    response_id = _require_string(
        content,
        'response_id',
        max_length=MAX_RESPONSE_ID_LENGTH,
    )
    return {
        'event_id': validate_optional_event_id(content.get('event_id')),
        'response_id': response_id,
    }


def parse_end_turn_event(content):
    return {
        'event_id': validate_optional_event_id(content.get('event_id')),
    }


def _require_string(content, field_name, *, max_length):
    value = content.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise RealtimeProtocolError(
            'invalid_payload',
            f'{field_name} must be a non-empty string.',
        )
    normalized = value.strip()
    if len(normalized) > max_length:
        raise RealtimeProtocolError(
            'invalid_payload',
            f'{field_name} is too long.',
        )
    return normalized


def _require_int(content, field_name, *, minimum, maximum):
    value = content.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise RealtimeProtocolError(
            'invalid_payload',
            f'{field_name} must be an integer.',
        )
    if value < minimum or value > maximum:
        raise RealtimeProtocolError(
            'invalid_payload',
            f'{field_name} is out of range.',
        )
    return value


def parse_audio_chunk_event(content):
    if any(field in content for field in ('payload', 'bytes')):
        raise RealtimeProtocolError(
            'audio_payload_not_supported',
            'Only base64 JSON audio payloads are supported in V5B-2.',
        )

    parsed = {
        'event_id': validate_optional_event_id(content.get('event_id')),
        'chunk_id': _require_string(
            content,
            'chunk_id',
            max_length=MAX_CHUNK_ID_LENGTH,
        ),
        'sequence': _require_int(
            content,
            'sequence',
            minimum=0,
            maximum=1_000_000,
        ),
        'mime_type': _require_string(
            content,
            'mime_type',
            max_length=MAX_MIME_TYPE_LENGTH,
        ),
        'size_bytes': _require_int(
            content,
            'size_bytes',
            minimum=0,
            maximum=MAX_CHUNK_SIZE_BYTES,
        ),
        'duration_ms': _require_int(
            content,
            'duration_ms',
            minimum=0,
            maximum=MAX_CHUNK_DURATION_MS,
        ),
        'is_final': bool(content.get('is_final', False)),
    }
    if not parsed['mime_type'].lower().startswith('audio/'):
        raise RealtimeProtocolError(
            'invalid_payload',
            'mime_type must be an audio/* content type.',
        )

    audio_base64 = _require_string(
        content,
        'audio_base64',
        max_length=MAX_BASE64_LENGTH,
    )
    try:
        decoded_bytes = base64.b64decode(audio_base64, validate=True)
    except (ValueError, binascii.Error):
        raise RealtimeProtocolError(
            'invalid_payload',
            'audio_base64 must be valid base64 data.',
        )

    if len(decoded_bytes) != parsed['size_bytes']:
        raise RealtimeProtocolError(
            'invalid_payload',
            'size_bytes does not match decoded audio payload size.',
        )

    parsed['audio_base64'] = audio_base64
    parsed['audio_bytes'] = decoded_bytes
    return parsed
