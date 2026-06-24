import asyncio
import base64
import logging
import os
import re
import time
from collections import deque

from django.conf import settings
from django.db.models import Count

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .models import VoiceConversationSession, VoiceConversationTurn
from .realtime_protocol import (
    RealtimeProtocolError,
    build_assistant_interrupted_event,
    build_ai_response_delta_event,
    build_ai_response_error_event,
    build_ai_response_final_event,
    build_ai_response_start_event,
    build_audio_chunk_ack_event,
    build_client_status_ack_event,
    build_connected_event,
    build_error_event,
    build_pong_event,
    build_realtime_turn_interrupted_event,
    build_realtime_turn_persisted_event,
    build_session_status_event,
    build_stt_status_event,
    build_tts_chunk_event,
    build_tts_complete_event,
    build_tts_error_event,
    build_tts_start_event,
    build_transcript_event,
    parse_assistant_playback_complete_event,
    parse_audio_chunk_event,
    parse_client_status_event,
    parse_interrupt_event,
    parse_ping_event,
)
from .serializers import VoiceConversationTurnSerializer
from .realtime_stt import (
    RealtimeSttConfigError,
    RealtimeSttError,
    create_realtime_stt_session,
)
from .voice_conversation_services import (
    create_realtime_voice_conversation_turn,
    generate_voice_conversation_response,
)
from .voice_services import VoiceDiagnosticConfigError, VoiceDiagnosticError, synthesize_tts


AI_RESPONSE_TARGET_CHARS = 48
TTS_AUDIO_CHUNK_SIZE_BYTES = 32 * 1024
RATE_LIMIT_WINDOW_SECONDS = 60

logger = logging.getLogger(__name__)


def _split_ai_response_text(response_text):
    parts = re.findall(r'\S+\s*', response_text)
    if not parts:
        return [response_text]

    chunks = []
    current_chunk = ''
    for part in parts:
        if current_chunk and len(current_chunk) + len(part) > AI_RESPONSE_TARGET_CHARS:
            chunks.append(current_chunk)
            current_chunk = part
            continue
        current_chunk += part

    if current_chunk:
        chunks.append(current_chunk)
    return chunks


def _split_audio_bytes(audio_content):
    return [
        audio_content[index:index + TTS_AUDIO_CHUNK_SIZE_BYTES]
        for index in range(0, len(audio_content), TTS_AUDIO_CHUNK_SIZE_BYTES)
    ]


def _int_setting(name, default):
    value = getattr(settings, name, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class VoiceConversationSessionConsumer(AsyncJsonWebsocketConsumer):
    CLOSE_CODE_UNAUTHENTICATED = 4401
    CLOSE_CODE_NOT_FOUND = 4404
    CLOSE_CODE_POLICY = 4408
    CLOSE_CODE_RATE_LIMITED = 4429

    async def connect(self):
        user = self.scope.get('user')
        if user is None or not user.is_authenticated:
            await self.close(code=self.CLOSE_CODE_UNAUTHENTICATED)
            return

        self.session_id = self.scope['url_route']['kwargs']['session_id']
        session = await self._get_owned_session(self.session_id, user.id)
        if session is None:
            await self.close(code=self.CLOSE_CODE_NOT_FOUND)
            return

        self.session_snapshot = session
        self.latest_client_status = {}
        self.realtime_stt_session = None
        self.realtime_stt_disabled = False
        self.active_ai_response_task = None
        self.ai_response_counter = 0
        self.last_ai_transcript = None
        self.last_ai_transcript_started_at = None
        self.current_assistant_response_id = None
        self.current_assistant_state = 'idle'
        self.interrupted_response_ids = set()
        self.persisted_realtime_turns = {}
        now = time.monotonic()
        self.connection_started_at = now
        self.last_client_event_at = now
        self.recent_event_timestamps = deque()
        self.recent_audio_chunk_timestamps = deque()
        self.recent_audio_byte_entries = deque()
        self.idle_watchdog_task = asyncio.create_task(self._idle_watchdog_loop())
        self.group_name = f'voice-conversation-session-{self.session_id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json(build_connected_event(self.session_id))
        await self.send_json(build_session_status_event(session))

    async def disconnect(self, close_code):
        await self._cancel_idle_watchdog_task()
        await self._cancel_active_ai_response_task()
        await self._close_realtime_stt_session()
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if not isinstance(content, dict):
            await self.send_json(
                build_error_event(
                    'invalid_payload',
                    'Realtime messages must be JSON objects.',
                )
            )
            return

        message_type = content.get('type')
        event_id = content.get('event_id')

        if not isinstance(message_type, str) or not message_type.strip():
            await self.send_json(
                build_error_event(
                    'invalid_payload',
                    'Realtime messages require a non-empty type.',
                    event_id=event_id,
                )
            )
            return

        self.last_client_event_at = time.monotonic()
        if not await self._register_event(message_type):
            return

        if message_type in {'get_session_status', 'session_status'}:
            session = await self._get_owned_session(self.session_id, self.scope['user'].id)
            if session is None:
                await self.send_json(
                    build_error_event(
                        'session_not_found',
                        'Voice conversation session not found.',
                        event_id=event_id,
                        for_type=message_type,
                    )
                )
                return
            self.session_snapshot = session
            await self.send_json(build_session_status_event(session))
            return

        try:
            if message_type in {'ping', 'heartbeat'}:
                ping_event = parse_ping_event(content)
                await self.send_json(
                    build_pong_event(
                        self.session_id,
                        event_id=ping_event['event_id'],
                        client_ts=ping_event['client_ts'],
                    )
                )
                return

            if message_type == 'client_status':
                client_status_event = parse_client_status_event(content)
                self.latest_client_status = client_status_event['status']
                await self.send_json(
                    build_client_status_ack_event(
                        self.session_id,
                        client_status_event['event_id'],
                        client_status_event['status'],
                    )
                )
                return

            if message_type == 'interrupt':
                interrupt_event = parse_interrupt_event(content)
                await self._interrupt_assistant_output(
                    trigger=interrupt_event['source'],
                    reason=interrupt_event['reason'],
                )
                return

            if message_type == 'assistant_playback_complete':
                playback_complete_event = parse_assistant_playback_complete_event(content)
                await self._complete_assistant_playback(playback_complete_event['response_id'])
                return

            if message_type == 'audio_chunk':
                audio_chunk_event = parse_audio_chunk_event(content)
                if not await self._register_audio_chunk(audio_chunk_event):
                    return
                await self.send_json(
                    build_audio_chunk_ack_event(
                        self.session_id,
                        audio_chunk_event['event_id'],
                        audio_chunk_event,
                    )
                )
                await self._forward_audio_chunk_to_stt(audio_chunk_event)
                return
        except RealtimeProtocolError as exc:
            await self.send_json(
                build_error_event(
                    exc.code,
                    exc.message,
                    event_id=event_id,
                    for_type=message_type,
                )
            )
            return

        await self.send_json(
            build_error_event(
                'unsupported_message',
                'Unsupported realtime message type.',
                event_id=event_id,
                for_type=message_type,
            )
        )

    async def _forward_audio_chunk_to_stt(self, audio_chunk_event):
        if self.realtime_stt_disabled:
            return

        if self.current_assistant_response_id is not None:
            await self._interrupt_assistant_output(
                trigger='learner_audio',
                reason='Learner audio took priority over the current AI output.',
            )

        try:
            if self.realtime_stt_session is None:
                self.realtime_stt_session = create_realtime_stt_session(
                    session_id=self.session_id,
                    mime_type=audio_chunk_event['mime_type'],
                    status_callback=self._handle_stt_status,
                    transcript_callback=self._handle_stt_transcript,
                )
                await asyncio.wait_for(
                    self.realtime_stt_session.start(),
                    timeout=_int_setting(
                        'VOICE_CONVERSATION_REALTIME_STT_FORWARD_TIMEOUT_SECONDS',
                        10,
                    ),
                )

            await asyncio.wait_for(
                self.realtime_stt_session.send_audio_chunk(
                    audio_chunk_event['audio_bytes'],
                    is_final=audio_chunk_event['is_final'],
                ),
                timeout=_int_setting(
                    'VOICE_CONVERSATION_REALTIME_STT_FORWARD_TIMEOUT_SECONDS',
                    10,
                ),
            )
        except RealtimeSttConfigError as exc:
            logger.warning(
                'Realtime STT is unavailable for session %s: %s',
                self.session_id,
                exc,
            )
            self.realtime_stt_disabled = True
            await self.send_json(
                build_stt_status_event(
                    self.session_id,
                    state='unavailable',
                    provider='deepgram',
                    message=(
                        'Realtime speech-to-text is unavailable. '
                        'Use the standard voice turn flow for this session.'
                    ),
                )
            )
            await self._close_realtime_stt_session()
        except asyncio.TimeoutError:
            logger.warning(
                'Realtime STT timed out for session %s while forwarding audio.',
                self.session_id,
            )
            await self._disable_realtime_stt(
                'Realtime speech-to-text timed out. '
                'Use the standard voice turn flow for this session.'
            )
        except RealtimeSttError as exc:
            logger.warning(
                'Realtime STT failed for session %s: %s',
                self.session_id,
                exc,
            )
            await self._disable_realtime_stt(
                'Realtime speech-to-text is unavailable. '
                'Use the standard voice turn flow for this session.'
            )
        except Exception as exc:
            logger.exception(
                'Unexpected realtime STT forwarding failure for session %s.',
                self.session_id,
            )
            await self._disable_realtime_stt(
                'Realtime speech-to-text is unavailable. '
                'Use the standard voice turn flow for this session.'
            )

    async def _handle_stt_status(self, *, state, provider, message):
        if state == 'error':
            logger.warning(
                'Realtime STT provider error for session %s: %s',
                self.session_id,
                message,
            )
            self.realtime_stt_disabled = True
            await self._close_realtime_stt_session()
            message = (
                'Realtime speech-to-text is unavailable. '
                'Use the standard voice turn flow for this session.'
            )
        await self.send_json(
            build_stt_status_event(
                self.session_id,
                state=state,
                provider=provider,
                message=message,
            )
        )

    async def _handle_stt_transcript(
        self,
        *,
        provider,
        transcript,
        is_final,
        speech_final,
        provider_event_type,
    ):
        await self.send_json(
            build_transcript_event(
                self.session_id,
                provider=provider,
                transcript=transcript,
                is_final=is_final,
                speech_final=speech_final,
                provider_event_type=provider_event_type,
            )
        )
        if is_final and transcript.strip():
            await self._start_ai_response_stream(transcript)

    async def _start_ai_response_stream(self, transcript):
        normalized_transcript = transcript.strip()
        if not normalized_transcript:
            return
        if self.active_ai_response_task and not self.active_ai_response_task.done():
            return
        duplicate_window = _int_setting(
            'VOICE_CONVERSATION_REALTIME_DUPLICATE_TRANSCRIPT_WINDOW_SECONDS',
            3,
        )
        now = time.monotonic()
        if (
            normalized_transcript == self.last_ai_transcript
            and self.last_ai_transcript_started_at is not None
            and now - self.last_ai_transcript_started_at < duplicate_window
        ):
            logger.info(
                'Skipping duplicate realtime transcript for session %s within %ss.',
                self.session_id,
                duplicate_window,
            )
            return

        self.last_ai_transcript = normalized_transcript
        self.last_ai_transcript_started_at = now
        self.ai_response_counter += 1
        response_id = f'ai-response-{self.ai_response_counter}'
        self.current_assistant_response_id = response_id
        self.current_assistant_state = 'streaming_ai'
        self.active_ai_response_task = asyncio.create_task(
            self._run_ai_response_stream(response_id, normalized_transcript)
        )

    async def _run_ai_response_stream(self, response_id, transcript):
        try:
            if not await self._send_response_event(
                response_id,
                build_ai_response_start_event(
                    self.session_id,
                    response_id=response_id,
                    transcript=transcript,
                ),
            ):
                return
            response_text, response_source = await asyncio.wait_for(
                self._generate_ai_response(transcript),
                timeout=_int_setting(
                    'VOICE_CONVERSATION_REALTIME_AI_TIMEOUT_SECONDS',
                    45,
                ),
            )
            if self._response_is_interrupted(response_id):
                return
            response_chunks = _split_ai_response_text(response_text)
            accumulated_text = ''
            for sequence, delta_text in enumerate(response_chunks, start=1):
                accumulated_text += delta_text
                if not await self._send_response_event(
                    response_id,
                    build_ai_response_delta_event(
                        self.session_id,
                        response_id=response_id,
                        sequence=sequence,
                        delta_text=delta_text,
                        accumulated_text=accumulated_text,
                    ),
                ):
                    return
                await asyncio.sleep(0)

            self.current_assistant_state = 'generating_tts'
            if not await self._send_response_event(
                response_id,
                build_ai_response_final_event(
                    self.session_id,
                    response_id=response_id,
                    response_text=response_text,
                    response_source=response_source,
                    chunk_count=len(response_chunks),
                ),
            ):
                return
            await self._stream_tts_audio(
                response_id,
                transcript,
                response_text,
                response_source,
            )
        except asyncio.CancelledError:
            raise
        except VoiceConversationSession.DoesNotExist:
            if self.current_assistant_response_id == response_id:
                self.current_assistant_response_id = None
                self.current_assistant_state = 'idle'
            await self.send_json(
                build_ai_response_error_event(
                    self.session_id,
                    response_id=response_id,
                    code='session_not_found',
                    message='Voice conversation session no longer exists.',
                )
            )
        except asyncio.TimeoutError:
            logger.warning(
                'Realtime AI response timed out for session %s.',
                self.session_id,
            )
            if self.current_assistant_response_id == response_id:
                self.current_assistant_response_id = None
                self.current_assistant_state = 'idle'
            await self.send_json(
                build_ai_response_error_event(
                    self.session_id,
                    response_id=response_id,
                    code='ai_response_timeout',
                    message=(
                        'Realtime response generation timed out. '
                        'Use the standard voice turn flow to continue.'
                    ),
                )
            )
        except Exception as exc:
            logger.exception(
                'Unexpected realtime AI response failure for session %s.',
                self.session_id,
            )
            if self.current_assistant_response_id == response_id:
                self.current_assistant_response_id = None
                self.current_assistant_state = 'idle'
            await self.send_json(
                build_ai_response_error_event(
                    self.session_id,
                    response_id=response_id,
                    code='ai_response_failed',
                    message=(
                        'Realtime response generation is unavailable right now. '
                        'Use the standard voice turn flow to continue.'
                    ),
                )
            )
        finally:
            if self.active_ai_response_task is asyncio.current_task():
                self.active_ai_response_task = None

    async def _stream_tts_audio(self, response_id, transcript, response_text, response_source):
        if self._response_is_interrupted(response_id):
            return
        try:
            audio_content, content_type = await asyncio.wait_for(
                asyncio.to_thread(
                    synthesize_tts,
                    response_text,
                ),
                timeout=_int_setting(
                    'VOICE_CONVERSATION_REALTIME_TTS_TIMEOUT_SECONDS',
                    45,
                ),
            )
            if self._response_is_interrupted(response_id):
                return
        except VoiceDiagnosticConfigError as exc:
            logger.warning(
                'Realtime TTS is unavailable for session %s: %s',
                self.session_id,
                exc,
            )
            turn = await self._persist_realtime_turn(
                response_id=response_id,
                transcript=transcript,
                response_text=response_text,
                response_source=response_source,
            )
            if turn is not None:
                await self.send_json(
                    build_realtime_turn_persisted_event(
                        self.session_id,
                        response_id=response_id,
                        turn=turn,
                    )
                )
            if self.current_assistant_response_id == response_id:
                self.current_assistant_response_id = None
                self.current_assistant_state = 'idle'
            await self._send_response_event(
                response_id,
                build_tts_error_event(
                    self.session_id,
                    response_id=response_id,
                    code='tts_unavailable',
                    message=(
                        'Realtime teacher audio is unavailable. '
                        'The text response was kept and the standard voice turn flow remains available.'
                    ),
                ),
            )
            return
        except asyncio.TimeoutError:
            logger.warning(
                'Realtime TTS timed out for session %s.',
                self.session_id,
            )
            turn = await self._persist_realtime_turn(
                response_id=response_id,
                transcript=transcript,
                response_text=response_text,
                response_source=response_source,
            )
            if turn is not None:
                await self.send_json(
                    build_realtime_turn_persisted_event(
                        self.session_id,
                        response_id=response_id,
                        turn=turn,
                    )
                )
            if self.current_assistant_response_id == response_id:
                self.current_assistant_response_id = None
                self.current_assistant_state = 'idle'
            await self._send_response_event(
                response_id,
                build_tts_error_event(
                    self.session_id,
                    response_id=response_id,
                    code='tts_timeout',
                    message=(
                        'Realtime teacher audio timed out. '
                        'The text response was kept and the standard voice turn flow remains available.'
                    ),
                ),
            )
            return
        except VoiceDiagnosticError as exc:
            logger.warning(
                'Realtime TTS failed for session %s: %s',
                self.session_id,
                exc,
            )
            turn = await self._persist_realtime_turn(
                response_id=response_id,
                transcript=transcript,
                response_text=response_text,
                response_source=response_source,
            )
            if turn is not None:
                await self.send_json(
                    build_realtime_turn_persisted_event(
                        self.session_id,
                        response_id=response_id,
                        turn=turn,
                    )
                )
            if self.current_assistant_response_id == response_id:
                self.current_assistant_response_id = None
                self.current_assistant_state = 'idle'
            await self._send_response_event(
                response_id,
                build_tts_error_event(
                    self.session_id,
                    response_id=response_id,
                    code='tts_failed',
                    message=(
                        'Realtime teacher audio is unavailable. '
                        'The text response was kept and the standard voice turn flow remains available.'
                    ),
                ),
            )
            return
        except Exception as exc:
            logger.exception(
                'Unexpected realtime TTS failure for session %s.',
                self.session_id,
            )
            turn = await self._persist_realtime_turn(
                response_id=response_id,
                transcript=transcript,
                response_text=response_text,
                response_source=response_source,
            )
            if turn is not None:
                await self.send_json(
                    build_realtime_turn_persisted_event(
                        self.session_id,
                        response_id=response_id,
                        turn=turn,
                    )
                )
            if self.current_assistant_response_id == response_id:
                self.current_assistant_response_id = None
                self.current_assistant_state = 'idle'
            await self._send_response_event(
                response_id,
                build_tts_error_event(
                    self.session_id,
                    response_id=response_id,
                    code='tts_failed',
                    message=(
                        'Realtime teacher audio is unavailable. '
                        'The text response was kept and the standard voice turn flow remains available.'
                    ),
                ),
            )
            return

        audio_chunks = _split_audio_bytes(audio_content)
        self.current_assistant_state = 'tts_streaming'
        if not await self._send_response_event(
            response_id,
            build_tts_start_event(
                self.session_id,
                response_id=response_id,
                provider='deepgram',
                content_type=content_type,
                total_size_bytes=len(audio_content),
                chunk_count=len(audio_chunks),
            ),
        ):
            return
        for sequence, audio_chunk in enumerate(audio_chunks, start=1):
            if not await self._send_response_event(
                response_id,
                build_tts_chunk_event(
                    self.session_id,
                    response_id=response_id,
                    sequence=sequence,
                    chunk_base64=base64.b64encode(audio_chunk).decode('ascii'),
                    size_bytes=len(audio_chunk),
                    is_final=sequence == len(audio_chunks),
                ),
            ):
                return
            await asyncio.sleep(0)

        turn = await self._persist_realtime_turn(
            response_id=response_id,
            transcript=transcript,
            response_text=response_text,
            response_source=response_source,
            ai_audio_content=audio_content,
            ai_audio_content_type=content_type,
        )
        if turn is not None:
            await self.send_json(
                build_realtime_turn_persisted_event(
                    self.session_id,
                    response_id=response_id,
                    turn=turn,
                )
            )

        self.current_assistant_state = 'awaiting_playback_completion'
        await self._send_response_event(
            response_id,
            build_tts_complete_event(
                self.session_id,
                response_id=response_id,
                provider='deepgram',
                content_type=content_type,
                total_size_bytes=len(audio_content),
                chunk_count=len(audio_chunks),
            ),
        )

    async def _cancel_idle_watchdog_task(self):
        task = getattr(self, 'idle_watchdog_task', None)
        self.idle_watchdog_task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return

    async def _idle_watchdog_loop(self):
        idle_timeout = _int_setting(
            'VOICE_CONVERSATION_REALTIME_IDLE_TIMEOUT_SECONDS',
            120,
        )
        poll_interval = max(
            1,
            _int_setting('VOICE_CONVERSATION_REALTIME_IDLE_POLL_SECONDS', 5),
        )
        if idle_timeout <= 0:
            return

        while True:
            await asyncio.sleep(poll_interval)
            if time.monotonic() - self.last_client_event_at <= idle_timeout:
                continue
            await self._close_with_error(
                code='idle_timeout',
                message=(
                    'Realtime voice connection closed after inactivity. '
                    'Reconnect or use the standard voice turn flow to continue.'
                ),
                close_code=self.CLOSE_CODE_POLICY,
            )
            return

    async def _register_event(self, message_type):
        max_events = _int_setting(
            'VOICE_CONVERSATION_REALTIME_MAX_EVENTS_PER_MINUTE',
            240,
        )
        now = time.monotonic()
        self._expire_recent_entries(self.recent_event_timestamps, now)
        if max_events > 0 and len(self.recent_event_timestamps) >= max_events:
            logger.warning(
                'Realtime event rate limit exceeded for session %s on message type %s.',
                self.session_id,
                message_type,
            )
            await self._close_with_error(
                code='rate_limited',
                message=(
                    'Realtime voice event rate limit exceeded. '
                    'Reconnect or use the standard voice turn flow to continue.'
                ),
                for_type=message_type,
                close_code=self.CLOSE_CODE_RATE_LIMITED,
            )
            return False
        self.recent_event_timestamps.append(now)
        return True

    async def _register_audio_chunk(self, audio_chunk_event):
        max_chunks = _int_setting(
            'VOICE_CONVERSATION_REALTIME_MAX_AUDIO_CHUNKS_PER_MINUTE',
            180,
        )
        max_bytes = _int_setting(
            'VOICE_CONVERSATION_REALTIME_MAX_AUDIO_BYTES_PER_MINUTE',
            8 * 1024 * 1024,
        )
        now = time.monotonic()
        self._expire_recent_entries(self.recent_audio_chunk_timestamps, now)
        self._expire_recent_audio_bytes(now)
        byte_count = sum(size for _, size in self.recent_audio_byte_entries)
        if max_chunks > 0 and len(self.recent_audio_chunk_timestamps) >= max_chunks:
            logger.warning(
                'Realtime audio chunk rate limit exceeded for session %s.',
                self.session_id,
            )
            await self._close_with_error(
                code='audio_rate_limited',
                message=(
                    'Realtime audio chunk rate limit exceeded. '
                    'Reconnect or use the standard voice turn flow to continue.'
                ),
                for_type='audio_chunk',
                close_code=self.CLOSE_CODE_RATE_LIMITED,
            )
            return False
        if max_bytes > 0 and byte_count + audio_chunk_event['size_bytes'] > max_bytes:
            logger.warning(
                'Realtime audio byte limit exceeded for session %s.',
                self.session_id,
            )
            await self._close_with_error(
                code='audio_rate_limited',
                message=(
                    'Realtime audio throughput limit exceeded. '
                    'Reconnect or use the standard voice turn flow to continue.'
                ),
                for_type='audio_chunk',
                close_code=self.CLOSE_CODE_RATE_LIMITED,
            )
            return False
        self.recent_audio_chunk_timestamps.append(now)
        self.recent_audio_byte_entries.append((now, audio_chunk_event['size_bytes']))
        return True

    @staticmethod
    def _expire_recent_entries(entries, now):
        while entries and now - entries[0] > RATE_LIMIT_WINDOW_SECONDS:
            entries.popleft()

    def _expire_recent_audio_bytes(self, now):
        while (
            self.recent_audio_byte_entries
            and now - self.recent_audio_byte_entries[0][0] > RATE_LIMIT_WINDOW_SECONDS
        ):
            self.recent_audio_byte_entries.popleft()

    async def _close_with_error(self, *, code, message, close_code, for_type=None):
        try:
            await self.send_json(
                build_error_event(
                    code,
                    message,
                    for_type=for_type,
                )
            )
        except Exception:
            logger.exception(
                'Failed to send realtime websocket error event for session %s.',
                self.session_id,
            )
        await self.close(code=close_code)

    async def _cancel_active_ai_response_task(self):
        task = self.active_ai_response_task
        self.active_ai_response_task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return

    async def _interrupt_assistant_output(self, *, trigger, reason):
        response_id = self.current_assistant_response_id
        previous_state = self.current_assistant_state
        had_active_response = response_id is not None
        if response_id is not None:
            self.interrupted_response_ids.add(response_id)
        self.current_assistant_response_id = None
        self.current_assistant_state = 'idle'
        await self._cancel_active_ai_response_task()
        await self.send_json(
            build_assistant_interrupted_event(
                self.session_id,
                response_id=response_id,
                trigger=trigger,
                reason=reason,
                previous_state=previous_state,
                had_active_response=had_active_response,
            )
        )
        persisted_turn = await self._mark_persisted_turn_interrupted(
            response_id=response_id,
            trigger=trigger,
            reason=reason,
        )
        if persisted_turn is not None:
            await self.send_json(
                build_realtime_turn_interrupted_event(
                    self.session_id,
                    response_id=response_id,
                    turn=persisted_turn,
                )
            )

    def _response_is_interrupted(self, response_id):
        if response_id in self.interrupted_response_ids:
            return True
        return self.current_assistant_response_id not in {None, response_id}

    async def _send_response_event(self, response_id, event):
        if self._response_is_interrupted(response_id):
            return False
        await self.send_json(event)
        return True

    async def _complete_assistant_playback(self, response_id):
        if self.current_assistant_response_id != response_id:
            return
        self.current_assistant_response_id = None
        self.current_assistant_state = 'idle'
        self.interrupted_response_ids.discard(response_id)

    async def _disable_realtime_stt(self, message):
        self.realtime_stt_disabled = True
        await self._close_realtime_stt_session()
        await self.send_json(
            build_stt_status_event(
                self.session_id,
                state='error',
                provider='deepgram',
                message=message,
            )
        )

    async def _close_realtime_stt_session(self):
        if self.realtime_stt_session is None:
            return
        session = self.realtime_stt_session
        self.realtime_stt_session = None
        try:
            await session.close()
        except Exception:
            logger.exception(
                'Realtime STT session cleanup failed for session %s.',
                self.session_id,
            )

    @database_sync_to_async
    def _get_owned_session(self, session_id, user_id):
        session = (
            VoiceConversationSession.objects.filter(pk=session_id, user_id=user_id)
            .annotate(turn_count=Count('turns'))
            .values('id', 'status', 'target_skill', 'cefr_level', 'turn_count')
            .first()
        )
        return session

    @database_sync_to_async
    def _generate_ai_response(self, transcript):
        session = VoiceConversationSession.objects.get(
            pk=self.session_id,
            user_id=self.scope['user'].id,
        )
        return generate_voice_conversation_response(session, transcript)

    async def _persist_realtime_turn(
        self,
        *,
        response_id,
        transcript,
        response_text,
        response_source,
        ai_audio_content=None,
        ai_audio_content_type=None,
    ):
        if self._response_is_interrupted(response_id):
            return None
        if response_id in self.persisted_realtime_turns:
            return self.persisted_realtime_turns[response_id]
        try:
            serialized_turn = await self._create_realtime_turn_record(
                response_id=response_id,
                transcript=transcript,
                response_text=response_text,
                response_source=response_source,
                ai_audio_content=ai_audio_content,
                ai_audio_content_type=ai_audio_content_type,
            )
        except Exception:
            logger.exception(
                'Realtime turn persistence failed for session %s response %s.',
                self.session_id,
                response_id,
            )
            return None
        self.persisted_realtime_turns[response_id] = serialized_turn
        return serialized_turn

    async def _mark_persisted_turn_interrupted(self, *, response_id, trigger, reason):
        if not response_id:
            return None

        cached_turn = self.persisted_realtime_turns.get(response_id)
        if cached_turn is None:
            try:
                updated_turn = await self._update_persisted_turn_interrupted(
                    response_id=response_id,
                    trigger=trigger,
                    reason=reason,
                )
            except Exception:
                logger.exception(
                    'Realtime interrupted-turn persistence failed for session %s response %s.',
                    self.session_id,
                    response_id,
                )
                return None
            if updated_turn is not None:
                self.persisted_realtime_turns[response_id] = updated_turn
            return updated_turn

        metadata = dict(cached_turn.get('metadata') or {})
        if metadata.get('interrupted') is True:
            return cached_turn

        try:
            updated_turn = await self._update_persisted_turn_interrupted(
                response_id=response_id,
                trigger=trigger,
                reason=reason,
            )
        except Exception:
            logger.exception(
                'Realtime interrupted-turn update failed for session %s response %s.',
                self.session_id,
                response_id,
            )
            updated_turn = None
        if updated_turn is not None:
            self.persisted_realtime_turns[response_id] = updated_turn
            return updated_turn

        metadata['interrupted'] = True
        metadata['interruption_trigger'] = trigger
        metadata['interruption_reason'] = reason
        cached_turn['metadata'] = metadata
        return cached_turn

    @database_sync_to_async
    def _create_realtime_turn_record(
        self,
        *,
        response_id,
        transcript,
        response_text,
        response_source,
        ai_audio_content=None,
        ai_audio_content_type=None,
    ):
        session = VoiceConversationSession.objects.get(
            pk=self.session_id,
            user_id=self.scope['user'].id,
        )
        ai_provider = (
            os.getenv('LLM_PROVIDER', 'openai').strip().lower()
            if response_source == 'llm'
            else 'deterministic_fallback'
        )
        turn = create_realtime_voice_conversation_turn(
            session=session,
            user=self.scope['user'],
            user_transcript=transcript,
            ai_response_text=response_text,
            response_id=response_id,
            response_source=response_source,
            stt_provider='deepgram',
            ai_provider=ai_provider,
            tts_provider='deepgram' if ai_audio_content is not None else None,
            ai_audio_content=ai_audio_content,
            ai_audio_content_type=ai_audio_content_type,
            interrupted=False,
            fallback_used=response_source != 'llm',
            metadata={},
        )
        return VoiceConversationTurnSerializer(turn).data

    @database_sync_to_async
    def _update_persisted_turn_interrupted(self, *, response_id, trigger, reason):
        turn = (
            VoiceConversationTurn.objects.filter(
                session_id=self.session_id,
                session__user_id=self.scope['user'].id,
                metadata__response_id=response_id,
            )
            .order_by('-id')
            .first()
        )
        if turn is None:
            return None

        metadata = dict(turn.metadata or {})
        metadata['interrupted'] = True
        metadata['interruption_trigger'] = trigger
        metadata['interruption_reason'] = reason
        turn.metadata = metadata
        turn.save(update_fields=['metadata'])
        return VoiceConversationTurnSerializer(turn).data
