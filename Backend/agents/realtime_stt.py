import asyncio
import logging
from contextlib import suppress

from django.conf import settings


logger = logging.getLogger(__name__)


class RealtimeSttError(Exception):
    pass


class RealtimeSttConfigError(RealtimeSttError):
    pass


class DeepgramRealtimeTranscriptionSession:
    def __init__(
        self,
        *,
        session_id,
        mime_type,
        status_callback,
        transcript_callback,
    ):
        self.session_id = session_id
        self.mime_type = mime_type
        self.status_callback = status_callback
        self.transcript_callback = transcript_callback
        self._loop = None
        self._client = None
        self._connection_cm = None
        self._connection = None
        self._keepalive_task = None
        self._closed = False

    async def start(self):
        api_key = getattr(settings, 'DEEPGRAM_API_KEY', '')
        if not api_key:
            raise RealtimeSttConfigError('Realtime speech-to-text is not configured yet.')

        try:
            from deepgram import AsyncDeepgramClient
            from deepgram.core.events import EventType
        except ImportError as exc:
            raise RealtimeSttConfigError(
                'Realtime speech-to-text dependency is not installed.'
            ) from exc

        self._loop = asyncio.get_running_loop()
        connect_kwargs = self._build_connect_kwargs()
        self._client = AsyncDeepgramClient(api_key=api_key)
        self._connection_cm = self._client.listen.v1.connect(**connect_kwargs)
        self._connection = await self._connection_cm.__aenter__()

        self._connection.on(
            EventType.OPEN,
            lambda _: self._schedule(
                self.status_callback(
                    state='ready',
                    provider='deepgram',
                    message='Deepgram realtime STT stream connected.',
                )
            ),
        )
        self._connection.on(
            EventType.MESSAGE,
            lambda message: self._schedule(self._handle_message(message)),
        )
        self._connection.on(
            EventType.CLOSE,
            lambda _: self._schedule(
                self.status_callback(
                    state='closed',
                    provider='deepgram',
                    message='Deepgram realtime STT stream closed.',
                )
            ),
        )
        self._connection.on(
            EventType.ERROR,
            lambda error: self._schedule(
                self.status_callback(
                    state='error',
                    provider='deepgram',
                    message=f'Deepgram realtime STT error: {error}',
                )
            ),
        )

        await self.status_callback(
            state='initializing',
            provider='deepgram',
            message='Opening Deepgram realtime STT stream.',
        )
        await self._connection.start_listening()
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())

    async def send_audio_chunk(self, audio_bytes, *, is_final):
        if self._connection is None:
            raise RealtimeSttError('Realtime STT stream is not connected.')

        await self._connection.send_media(audio_bytes)
        if is_final:
            await self.status_callback(
                state='finalizing',
                provider='deepgram',
                message='Finalizing realtime STT transcript.',
            )
            await self._connection.send_finalize()

    async def close(self):
        if self._closed:
            return
        self._closed = True

        if self._keepalive_task is not None:
            self._keepalive_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._keepalive_task
            self._keepalive_task = None

        if self._connection is not None:
            with suppress(Exception):
                await self._connection.send_close_stream()

        if self._connection_cm is not None:
            with suppress(Exception):
                await self._connection_cm.__aexit__(None, None, None)

        self._connection = None
        self._connection_cm = None

    def _build_connect_kwargs(self):
        kwargs = {
            'model': getattr(settings, 'DEEPGRAM_REALTIME_STT_MODEL', '')
            or getattr(settings, 'DEEPGRAM_STT_MODEL', 'nova-3')
            or 'nova-3',
            'interim_results': 'true',
            'punctuate': 'true',
            'smart_format': 'true',
            'vad_events': 'true',
        }

        language = getattr(settings, 'DEEPGRAM_REALTIME_STT_LANGUAGE', '')
        if language:
            kwargs['language'] = language

        utterance_end_ms = getattr(settings, 'DEEPGRAM_REALTIME_STT_UTTERANCE_END_MS', 1200)
        if utterance_end_ms:
            kwargs['utterance_end_ms'] = str(utterance_end_ms)

        return kwargs

    async def _handle_message(self, message):
        message_type = getattr(message, 'type', '') or ''
        if message_type == 'SpeechStarted':
            await self.status_callback(
                state='listening',
                provider='deepgram',
                message='Speech detected by Deepgram.',
            )
            return

        if message_type == 'UtteranceEnd':
            await self.status_callback(
                state='utterance_end',
                provider='deepgram',
                message='Deepgram detected the end of an utterance.',
            )
            return

        if message_type != 'Results':
            return

        transcript = self._extract_transcript(message).strip()
        if not transcript:
            return

        await self.transcript_callback(
            provider='deepgram',
            transcript=transcript,
            is_final=bool(getattr(message, 'is_final', False)),
            speech_final=bool(getattr(message, 'speech_final', False)),
            provider_event_type=message_type,
        )

    def _extract_transcript(self, message):
        results = getattr(message, 'results', None)
        channels = getattr(results, 'channels', None) if results is not None else None
        if not channels:
            return ''

        first_channel = channels[0]
        alternatives = getattr(first_channel, 'alternatives', None)
        if not alternatives:
            return ''

        first_alternative = alternatives[0]
        transcript = getattr(first_alternative, 'transcript', '')
        return transcript or ''

    async def _keepalive_loop(self):
        interval = getattr(settings, 'DEEPGRAM_REALTIME_STT_KEEPALIVE_SECONDS', 8)
        while True:
            await asyncio.sleep(interval)
            if self._connection is None:
                return
            try:
                await self._connection.send_keep_alive()
            except Exception as exc:
                logger.warning(
                    'Deepgram realtime STT keepalive failed for session %s: %s',
                    self.session_id,
                    exc,
                )
                await self.status_callback(
                    state='error',
                    provider='deepgram',
                    message=f'Deepgram realtime STT keepalive failed: {exc}',
                )
                return

    def _schedule(self, coroutine):
        if self._loop is None or self._loop.is_closed():
            return

        def runner():
            task = self._loop.create_task(coroutine)
            task.add_done_callback(self._log_task_failure)

        self._loop.call_soon_threadsafe(runner)

    @staticmethod
    def _log_task_failure(task):
        exc = task.exception()
        if exc is not None:
            logger.warning('Realtime STT callback failed: %s', exc)


def create_realtime_stt_session(*, session_id, mime_type, status_callback, transcript_callback):
    return DeepgramRealtimeTranscriptionSession(
        session_id=session_id,
        mime_type=mime_type,
        status_callback=status_callback,
        transcript_callback=transcript_callback,
    )
