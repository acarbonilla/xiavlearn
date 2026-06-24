from importlib import import_module
from uuid import uuid4
from unittest.mock import patch

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.contrib.auth import (
    BACKEND_SESSION_KEY,
    HASH_SESSION_KEY,
    SESSION_KEY,
)
from django.contrib.auth.models import User
from django.test import TransactionTestCase, override_settings

from agents.models import VoiceConversationSession, VoiceConversationTurn
from agents.realtime_stt import RealtimeSttConfigError
from agents.voice_services import VoiceDiagnosticError
from xiavlearn.asgi import application


class FakeRealtimeSttSession:
    def __init__(self, *, status_callback, transcript_callback, **kwargs):
        self.status_callback = status_callback
        self.transcript_callback = transcript_callback
        self.sent_chunks = []
        self.closed = False

    async def start(self):
        await self.status_callback(
            state='ready',
            provider='deepgram',
            message='Deepgram realtime STT stream connected.',
        )

    async def send_audio_chunk(self, audio_bytes, *, is_final):
        self.sent_chunks.append((audio_bytes, is_final))
        await self.transcript_callback(
            provider='deepgram',
            transcript='hello teacher',
            is_final=False,
            speech_final=False,
            provider_event_type='Results',
        )
        if is_final:
            await self.transcript_callback(
                provider='deepgram',
                transcript='hello teacher today',
                is_final=True,
                speech_final=True,
                provider_event_type='Results',
            )

    async def close(self):
        self.closed = True


class VoiceConversationRealtimeTests(TransactionTestCase):
    DEFAULT_ORIGIN = 'http://localhost:3000'

    def setUp(self):
        username_suffix = uuid4().hex
        self.user = User.objects.create_user(
            username=f'realtime-user-{username_suffix}',
            password='test-password-123',
        )
        self.other_user = User.objects.create_user(
            username=f'other-realtime-user-{username_suffix}',
            password='test-password-123',
        )
        self.session = VoiceConversationSession.objects.create(
            user=self.user,
            title='Realtime Practice',
            target_skill=VoiceConversationSession.TARGET_SKILL_SPEAKING,
            cefr_level='A2',
        )

    def _session_cookie(self, user):
        engine = import_module(settings.SESSION_ENGINE)
        session_store = engine.SessionStore()
        session_store[SESSION_KEY] = user.pk
        session_store[BACKEND_SESSION_KEY] = 'django.contrib.auth.backends.ModelBackend'
        session_store[HASH_SESSION_KEY] = user.get_session_auth_hash()
        session_store.save()
        return f'sessionid={session_store.session_key}'

    def _communicator(self, path, session_cookie=None, origin=None):
        headers = [
            (b'origin', (origin or self.DEFAULT_ORIGIN).encode()),
        ]
        if session_cookie is not None:
            headers.append((b'cookie', session_cookie.encode()))
        return WebsocketCommunicator(application, path, headers=headers)

    def test_owner_can_connect_and_receives_session_status(self):
        VoiceConversationTurn.objects.create(
            session=self.session,
            turn_number=1,
            user_transcript='Hello teacher.',
            ai_response_text='Practice feedback only: Keep going. Teacher follow-up: What happened next?',
        )
        owner_cookie = self._session_cookie(self.user)

        async def scenario():
            communicator = self._communicator(
                f'/ws/voice-conversation/sessions/{self.session.id}/',
                session_cookie=owner_cookie,
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            connected_event = await communicator.receive_json_from()
            status_event = await communicator.receive_json_from()

            self.assertEqual(connected_event['type'], 'connected')
            self.assertEqual(connected_event['session_id'], self.session.id)
            self.assertEqual(connected_event['protocol_version'], 'v5b-7')
            self.assertEqual(connected_event['realtime_stage'], 'persistence_fallback')
            self.assertEqual(status_event['type'], 'session_status')
            self.assertEqual(status_event['protocol_version'], 'v5b-7')
            self.assertEqual(status_event['session']['id'], self.session.id)
            self.assertEqual(status_event['session']['status'], 'active')
            self.assertEqual(status_event['session']['target_skill'], 'speaking')
            self.assertEqual(status_event['session']['turn_count'], 1)
            self.assertTrue(status_event['session']['practice_only'])
            self.assertEqual(status_event['session']['realtime_stage'], 'persistence_fallback')

            await communicator.disconnect()

        async_to_sync(scenario)()

    def test_unauthenticated_connection_is_rejected(self):
        async def scenario():
            communicator = self._communicator(
                f'/ws/voice-conversation/sessions/{self.session.id}/',
            )
            connected, close_code = await communicator.connect()
            self.assertFalse(connected)
            self.assertEqual(close_code, 4401)

        async_to_sync(scenario)()

    def test_user_cannot_connect_to_another_users_session(self):
        other_user_cookie = self._session_cookie(self.other_user)

        async def scenario():
            communicator = self._communicator(
                f'/ws/voice-conversation/sessions/{self.session.id}/',
                session_cookie=other_user_cookie,
            )
            connected, close_code = await communicator.connect()
            self.assertFalse(connected)
            self.assertEqual(close_code, 4404)

        async_to_sync(scenario)()

    @patch('agents.consumers.create_realtime_stt_session')
    def test_ping_client_status_audio_ack_and_status_messages_work(
        self,
        create_realtime_stt_session,
    ):
        session_holder = {}

        def create_session(**kwargs):
            session = FakeRealtimeSttSession(**kwargs)
            session_holder['session'] = session
            return session

        create_realtime_stt_session.side_effect = create_session
        owner_cookie = self._session_cookie(self.user)

        async def scenario():
            communicator = self._communicator(
                f'/ws/voice-conversation/sessions/{self.session.id}/',
                session_cookie=owner_cookie,
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.receive_json_from()
            await communicator.receive_json_from()

            await communicator.send_json_to(
                {
                    'type': 'ping',
                    'event_id': 'ping-1',
                    'client_ts': '2026-06-25T00:00:00Z',
                }
            )
            heartbeat_event = await communicator.receive_json_from()
            self.assertEqual(
                heartbeat_event,
                {
                    'type': 'pong',
                    'session_id': self.session.id,
                    'protocol_version': 'v5b-7',
                    'event_id': 'ping-1',
                    'client_ts': '2026-06-25T00:00:00Z',
                    'server_ts': heartbeat_event['server_ts'],
                },
            )
            self.assertTrue(heartbeat_event['server_ts'])

            await communicator.send_json_to(
                {
                    'type': 'client_status',
                    'event_id': 'status-1',
                    'status': {
                        'capture_state': 'idle',
                        'input_mode': 'transcript',
                        'mic_available': False,
                        'chunk_sequence': 0,
                    },
                }
            )
            echo_event = await communicator.receive_json_from()
            self.assertEqual(echo_event['type'], 'client_status_ack')
            self.assertEqual(echo_event['session_id'], self.session.id)
            self.assertEqual(echo_event['protocol_version'], 'v5b-7')
            self.assertEqual(echo_event['event_id'], 'status-1')
            self.assertTrue(echo_event['accepted'])
            self.assertEqual(
                echo_event['accepted_fields'],
                ['capture_state', 'chunk_sequence', 'input_mode', 'mic_available'],
            )

            await communicator.send_json_to(
                {
                    'type': 'audio_chunk',
                    'event_id': 'chunk-ack-1',
                    'chunk_id': 'chunk-1',
                    'sequence': 1,
                    'mime_type': 'audio/webm',
                    'size_bytes': 3,
                    'duration_ms': 1000,
                    'is_final': False,
                    'audio_base64': 'AQID',
                }
            )
            audio_ack_event = await communicator.receive_json_from()
            stt_status_event = await communicator.receive_json_from()
            partial_transcript_event = await communicator.receive_json_from()

            self.assertEqual(audio_ack_event['type'], 'audio_chunk_ack')
            self.assertEqual(audio_ack_event['session_id'], self.session.id)
            self.assertEqual(audio_ack_event['protocol_version'], 'v5b-7')
            self.assertEqual(audio_ack_event['event_id'], 'chunk-ack-1')
            self.assertEqual(audio_ack_event['chunk_id'], 'chunk-1')
            self.assertEqual(audio_ack_event['sequence'], 1)
            self.assertEqual(audio_ack_event['size_bytes'], 3)
            self.assertTrue(audio_ack_event['accepted'])
            self.assertEqual(audio_ack_event['ingest_stage'], 'base64_validated')
            self.assertTrue(audio_ack_event['server_ts'])

            self.assertEqual(stt_status_event['type'], 'stt_status')
            self.assertEqual(stt_status_event['state'], 'ready')
            self.assertEqual(stt_status_event['provider'], 'deepgram')
            self.assertEqual(stt_status_event['protocol_version'], 'v5b-7')

            self.assertEqual(partial_transcript_event['type'], 'transcript_partial')
            self.assertEqual(partial_transcript_event['provider'], 'deepgram')
            self.assertEqual(partial_transcript_event['transcript'], 'hello teacher')
            self.assertFalse(partial_transcript_event['is_final'])
            self.assertFalse(partial_transcript_event['speech_final'])

            await communicator.send_json_to({'type': 'get_session_status'})
            status_event = await communicator.receive_json_from()
            self.assertEqual(status_event['type'], 'session_status')
            self.assertEqual(status_event['session']['turn_count'], 0)

            await communicator.send_json_to(
                {
                    'type': 'unsupported',
                    'event_id': 'bad-1',
                }
            )
            error_event = await communicator.receive_json_from()
            self.assertEqual(error_event['type'], 'error')
            self.assertEqual(error_event['code'], 'unsupported_message')
            self.assertEqual(error_event['event_id'], 'bad-1')
            self.assertEqual(error_event['for_type'], 'unsupported')

            await communicator.disconnect()

        async_to_sync(scenario)()
        self.assertEqual(session_holder['session'].sent_chunks, [(b'\x01\x02\x03', False)])
        self.assertTrue(session_holder['session'].closed)

    @patch('agents.consumers.create_realtime_stt_session')
    def test_final_audio_chunk_emits_final_transcript_ai_stream_and_tts(
        self,
        create_realtime_stt_session,
    ):
        session_holder = {}

        def create_session(**kwargs):
            session = FakeRealtimeSttSession(**kwargs)
            session_holder['session'] = session
            return session

        create_realtime_stt_session.side_effect = create_session
        owner_cookie = self._session_cookie(self.user)
        streamed_response = (
            'Practice feedback only: Good detail. Teacher follow-up: '
            'What happened after that?'
        )

        with patch(
            'agents.consumers.generate_voice_conversation_response',
            return_value=(streamed_response, 'deterministic_fallback'),
        ), patch(
            'agents.consumers.synthesize_tts',
            return_value=(b'fake-realtime-tts', 'audio/mpeg'),
        ):
            async def scenario():
                communicator = self._communicator(
                    f'/ws/voice-conversation/sessions/{self.session.id}/',
                    session_cookie=owner_cookie,
                )
                connected, _ = await communicator.connect()
                self.assertTrue(connected)
                await communicator.receive_json_from()
                await communicator.receive_json_from()

                await communicator.send_json_to(
                    {
                        'type': 'audio_chunk',
                        'event_id': 'chunk-final-1',
                        'chunk_id': 'chunk-final-1',
                        'sequence': 1,
                        'mime_type': 'audio/webm',
                        'size_bytes': 3,
                        'duration_ms': 1000,
                        'is_final': True,
                        'audio_base64': 'AQID',
                    }
                )

                await communicator.receive_json_from()
                await communicator.receive_json_from()
                await communicator.receive_json_from()
                final_transcript_event = await communicator.receive_json_from()
                self.assertEqual(final_transcript_event['type'], 'transcript_final')
                self.assertEqual(final_transcript_event['transcript'], 'hello teacher today')
                self.assertTrue(final_transcript_event['is_final'])
                self.assertTrue(final_transcript_event['speech_final'])
                self.assertEqual(final_transcript_event['provider'], 'deepgram')

                ai_start_event = await communicator.receive_json_from()
                self.assertEqual(ai_start_event['type'], 'ai_response_start')
                self.assertEqual(ai_start_event['protocol_version'], 'v5b-7')
                self.assertEqual(ai_start_event['transcript'], 'hello teacher today')
                self.assertTrue(ai_start_event['practice_only'])

                ai_delta_events = []
                while True:
                    event = await communicator.receive_json_from()
                    if event['type'] == 'ai_response_final':
                        ai_final_event = event
                        break
                    ai_delta_events.append(event)

                self.assertTrue(ai_delta_events)
                self.assertTrue(
                    all(event['type'] == 'ai_response_delta' for event in ai_delta_events)
                )
                self.assertEqual(ai_final_event['protocol_version'], 'v5b-7')
                self.assertEqual(ai_final_event['response_text'], streamed_response)
                self.assertEqual(ai_final_event['response_source'], 'deterministic_fallback')
                self.assertEqual(ai_final_event['chunk_count'], len(ai_delta_events))
                self.assertTrue(ai_final_event['practice_only'])

                streamed_text = ''.join(
                    event['delta_text'] for event in ai_delta_events
                )
                self.assertEqual(streamed_text, streamed_response)
                self.assertEqual(
                    ai_delta_events[-1]['accumulated_text'],
                    streamed_response,
                )

                tts_start_event = await communicator.receive_json_from()
                tts_chunk_event = await communicator.receive_json_from()
                persisted_turn_event = await communicator.receive_json_from()
                tts_complete_event = await communicator.receive_json_from()

                self.assertEqual(tts_start_event['type'], 'tts_audio_start')
                self.assertEqual(tts_start_event['protocol_version'], 'v5b-7')
                self.assertEqual(tts_start_event['provider'], 'deepgram')
                self.assertEqual(tts_start_event['content_type'], 'audio/mpeg')
                self.assertEqual(tts_start_event['chunk_count'], 1)
                self.assertTrue(tts_start_event['practice_only'])

                self.assertEqual(tts_chunk_event['type'], 'tts_audio_chunk')
                self.assertEqual(tts_chunk_event['response_id'], ai_final_event['response_id'])
                self.assertEqual(tts_chunk_event['sequence'], 1)
                self.assertEqual(tts_chunk_event['audio_base64'], 'ZmFrZS1yZWFsdGltZS10dHM=')
                self.assertEqual(tts_chunk_event['size_bytes'], len(b'fake-realtime-tts'))
                self.assertTrue(tts_chunk_event['is_final'])

                self.assertEqual(tts_complete_event['type'], 'tts_audio_complete')
                self.assertEqual(tts_complete_event['content_type'], 'audio/mpeg')
                self.assertEqual(tts_complete_event['chunk_count'], 1)
                self.assertTrue(tts_complete_event['practice_only'])

                self.assertEqual(persisted_turn_event['type'], 'realtime_turn_persisted')
                self.assertEqual(persisted_turn_event['protocol_version'], 'v5b-7')
                self.assertEqual(
                    persisted_turn_event['response_id'],
                    ai_final_event['response_id'],
                )
                self.assertEqual(
                    persisted_turn_event['turn']['transcript_source'],
                    'deepgram_streaming',
                )
                self.assertEqual(
                    persisted_turn_event['turn']['user_transcript'],
                    'hello teacher today',
                )
                self.assertEqual(
                    persisted_turn_event['turn']['ai_response_text'],
                    streamed_response,
                )
                self.assertIsNotNone(persisted_turn_event['turn']['ai_audio'])
                self.assertEqual(
                    persisted_turn_event['turn']['metadata']['mode'],
                    'realtime',
                )
                self.assertEqual(
                    persisted_turn_event['turn']['metadata']['service_version'],
                    'v5b-7',
                )
                self.assertEqual(
                    persisted_turn_event['turn']['metadata']['response_id'],
                    ai_final_event['response_id'],
                )
                self.assertEqual(
                    persisted_turn_event['turn']['metadata']['stt_provider'],
                    'deepgram',
                )
                self.assertEqual(
                    persisted_turn_event['turn']['metadata']['ai_provider'],
                    'deterministic_fallback',
                )
                self.assertEqual(
                    persisted_turn_event['turn']['metadata']['tts_provider'],
                    'deepgram',
                )
                self.assertFalse(
                    persisted_turn_event['turn']['metadata']['interrupted']
                )
                self.assertTrue(
                    persisted_turn_event['turn']['metadata']['fallback_used']
                )
                self.assertTrue(
                    persisted_turn_event['turn']['metadata']['tts_generated']
                )

                await communicator.send_json_to(
                    {
                        'type': 'assistant_playback_complete',
                        'event_id': 'playback-complete-1',
                        'response_id': ai_final_event['response_id'],
                    }
                )

                await communicator.disconnect()

            async_to_sync(scenario)()
        self.assertEqual(session_holder['session'].sent_chunks, [(b'\x01\x02\x03', True)])
        self.assertEqual(VoiceConversationTurn.objects.count(), 1)
        saved_turn = VoiceConversationTurn.objects.get()
        self.assertEqual(
            saved_turn.transcript_source,
            VoiceConversationTurn.TRANSCRIPT_SOURCE_DEEPGRAM_STREAMING,
        )
        self.assertEqual(saved_turn.user_transcript, 'hello teacher today')
        self.assertEqual(saved_turn.ai_response_text, streamed_response)
        self.assertTrue(saved_turn.ai_audio)
        self.assertEqual(saved_turn.metadata['mode'], 'realtime')
        self.assertEqual(saved_turn.metadata['service_version'], 'v5b-7')
        self.assertFalse(saved_turn.metadata['interrupted'])

    @patch('agents.consumers.create_realtime_stt_session')
    def test_ai_generation_failure_emits_ai_response_error(self, create_realtime_stt_session):
        session_holder = {}

        def create_session(**kwargs):
            session = FakeRealtimeSttSession(**kwargs)
            session_holder['session'] = session
            return session

        create_realtime_stt_session.side_effect = create_session
        owner_cookie = self._session_cookie(self.user)

        with patch(
            'agents.consumers.generate_voice_conversation_response',
            side_effect=RuntimeError('LLM offline'),
        ):
            async def scenario():
                communicator = self._communicator(
                    f'/ws/voice-conversation/sessions/{self.session.id}/',
                    session_cookie=owner_cookie,
                )
                connected, _ = await communicator.connect()
                self.assertTrue(connected)
                await communicator.receive_json_from()
                await communicator.receive_json_from()

                await communicator.send_json_to(
                    {
                        'type': 'audio_chunk',
                        'event_id': 'chunk-ai-error-1',
                        'chunk_id': 'chunk-ai-error-1',
                        'sequence': 1,
                        'mime_type': 'audio/webm',
                        'size_bytes': 3,
                        'duration_ms': 1000,
                        'is_final': True,
                        'audio_base64': 'AQID',
                    }
                )

                await communicator.receive_json_from()
                await communicator.receive_json_from()
                await communicator.receive_json_from()
                await communicator.receive_json_from()
                ai_start_event = await communicator.receive_json_from()
                ai_error_event = await communicator.receive_json_from()

                self.assertEqual(ai_start_event['type'], 'ai_response_start')
                self.assertEqual(ai_error_event['type'], 'ai_response_error')
                self.assertEqual(ai_error_event['code'], 'ai_response_failed')
                self.assertEqual(
                    ai_error_event['message'],
                    (
                        'Realtime response generation is unavailable right now. '
                        'Use the standard voice turn flow to continue.'
                    ),
                )

                await communicator.disconnect()

            async_to_sync(scenario)()
        self.assertEqual(session_holder['session'].sent_chunks, [(b'\x01\x02\x03', True)])

    @patch('agents.consumers.create_realtime_stt_session')
    def test_tts_failure_emits_tts_audio_error(self, create_realtime_stt_session):
        session_holder = {}

        def create_session(**kwargs):
            session = FakeRealtimeSttSession(**kwargs)
            session_holder['session'] = session
            return session

        create_realtime_stt_session.side_effect = create_session
        owner_cookie = self._session_cookie(self.user)
        streamed_response = (
            'Practice feedback only: Good detail. Teacher follow-up: '
            'What happened after that?'
        )

        with patch(
            'agents.consumers.generate_voice_conversation_response',
            return_value=(streamed_response, 'deterministic_fallback'),
        ), patch(
            'agents.consumers.synthesize_tts',
            side_effect=VoiceDiagnosticError('TTS request failed: timeout'),
        ):
            async def scenario():
                communicator = self._communicator(
                    f'/ws/voice-conversation/sessions/{self.session.id}/',
                    session_cookie=owner_cookie,
                )
                connected, _ = await communicator.connect()
                self.assertTrue(connected)
                await communicator.receive_json_from()
                await communicator.receive_json_from()

                await communicator.send_json_to(
                    {
                        'type': 'audio_chunk',
                        'event_id': 'chunk-tts-error-1',
                        'chunk_id': 'chunk-tts-error-1',
                        'sequence': 1,
                        'mime_type': 'audio/webm',
                        'size_bytes': 3,
                        'duration_ms': 1000,
                        'is_final': True,
                        'audio_base64': 'AQID',
                    }
                )

                await communicator.receive_json_from()
                await communicator.receive_json_from()
                await communicator.receive_json_from()
                await communicator.receive_json_from()
                await communicator.receive_json_from()
                while True:
                    event = await communicator.receive_json_from()
                    if event['type'] == 'ai_response_final':
                        ai_final_event = event
                        break
                persisted_turn_event = await communicator.receive_json_from()
                tts_error_event = await communicator.receive_json_from()

                self.assertEqual(persisted_turn_event['type'], 'realtime_turn_persisted')
                self.assertEqual(
                    persisted_turn_event['response_id'],
                    ai_final_event['response_id'],
                )
                self.assertEqual(
                    persisted_turn_event['turn']['transcript_source'],
                    'deepgram_streaming',
                )
                self.assertIsNone(persisted_turn_event['turn']['ai_audio'])
                self.assertFalse(
                    persisted_turn_event['turn']['metadata']['tts_generated']
                )
                self.assertTrue(
                    persisted_turn_event['turn']['metadata']['fallback_used']
                )
                self.assertEqual(tts_error_event['type'], 'tts_audio_error')
                self.assertEqual(tts_error_event['code'], 'tts_failed')
                self.assertEqual(
                    tts_error_event['message'],
                    (
                        'Realtime teacher audio is unavailable. '
                        'The text response was kept and the standard voice turn flow remains available.'
                    ),
                )

                await communicator.disconnect()

            async_to_sync(scenario)()
        self.assertEqual(session_holder['session'].sent_chunks, [(b'\x01\x02\x03', True)])
        self.assertEqual(VoiceConversationTurn.objects.count(), 1)
        saved_turn = VoiceConversationTurn.objects.get()
        self.assertFalse(saved_turn.ai_audio)
        self.assertFalse(saved_turn.metadata['tts_generated'])
        self.assertFalse(saved_turn.metadata['interrupted'])

    @patch('agents.consumers.create_realtime_stt_session')
    def test_explicit_interrupt_stops_current_assistant_output(self, create_realtime_stt_session):
        session_holder = {}

        def create_session(**kwargs):
            session = FakeRealtimeSttSession(**kwargs)
            session_holder['session'] = session
            return session

        create_realtime_stt_session.side_effect = create_session
        owner_cookie = self._session_cookie(self.user)
        streamed_response = (
            'Practice feedback only: Good detail. Teacher follow-up: '
            'What happened after that?'
        )

        with patch(
            'agents.consumers.generate_voice_conversation_response',
            return_value=(streamed_response, 'deterministic_fallback'),
        ), patch(
            'agents.consumers.synthesize_tts',
            return_value=(b'fake-realtime-tts', 'audio/mpeg'),
        ):
            async def scenario():
                communicator = self._communicator(
                    f'/ws/voice-conversation/sessions/{self.session.id}/',
                    session_cookie=owner_cookie,
                )
                connected, _ = await communicator.connect()
                self.assertTrue(connected)
                await communicator.receive_json_from()
                await communicator.receive_json_from()

                await communicator.send_json_to(
                    {
                        'type': 'audio_chunk',
                        'event_id': 'chunk-for-interrupt-1',
                        'chunk_id': 'chunk-for-interrupt-1',
                        'sequence': 1,
                        'mime_type': 'audio/webm',
                        'size_bytes': 3,
                        'duration_ms': 1000,
                        'is_final': True,
                        'audio_base64': 'AQID',
                    }
                )

                while True:
                    event = await communicator.receive_json_from()
                    if event['type'] == 'realtime_turn_persisted':
                        persisted_turn_event = event
                    elif event['type'] == 'tts_audio_complete':
                        completed_tts_event = event
                        break

                await communicator.send_json_to(
                    {
                        'type': 'interrupt',
                        'event_id': 'interrupt-1',
                        'source': 'interrupt_button',
                        'reason': 'Learner started speaking over teacher playback.',
                    }
                )
                interrupt_event = await communicator.receive_json_from()
                interrupted_turn_event = await communicator.receive_json_from()

                self.assertEqual(interrupt_event['type'], 'assistant_interrupted')
                self.assertEqual(interrupt_event['protocol_version'], 'v5b-7')
                self.assertEqual(interrupt_event['response_id'], completed_tts_event['response_id'])
                self.assertEqual(interrupt_event['trigger'], 'interrupt_button')
                self.assertEqual(
                    interrupt_event['reason'],
                    'Learner started speaking over teacher playback.',
                )
                self.assertEqual(interrupt_event['previous_state'], 'awaiting_playback_completion')
                self.assertTrue(interrupt_event['had_active_response'])
                self.assertTrue(interrupt_event['stop_playback'])
                self.assertEqual(persisted_turn_event['type'], 'realtime_turn_persisted')
                self.assertEqual(
                    interrupted_turn_event['type'],
                    'realtime_turn_interrupted',
                )
                self.assertEqual(
                    interrupted_turn_event['response_id'],
                    completed_tts_event['response_id'],
                )
                self.assertTrue(interrupted_turn_event['turn']['metadata']['interrupted'])
                self.assertEqual(
                    interrupted_turn_event['turn']['metadata']['interruption_trigger'],
                    'interrupt_button',
                )

                await communicator.disconnect()

            async_to_sync(scenario)()
        self.assertEqual(session_holder['session'].sent_chunks, [(b'\x01\x02\x03', True)])
        saved_turn = VoiceConversationTurn.objects.get()
        self.assertTrue(saved_turn.metadata['interrupted'])
        self.assertEqual(saved_turn.metadata['interruption_trigger'], 'interrupt_button')

    @patch('agents.consumers.create_realtime_stt_session')
    def test_new_audio_interrupts_old_teacher_output_and_prioritizes_stt(
        self,
        create_realtime_stt_session,
    ):
        session_holder = {}

        def create_session(**kwargs):
            session = FakeRealtimeSttSession(**kwargs)
            session_holder['session'] = session
            return session

        create_realtime_stt_session.side_effect = create_session
        owner_cookie = self._session_cookie(self.user)
        streamed_response = (
            'Practice feedback only: Good detail. Teacher follow-up: '
            'What happened after that?'
        )

        with patch(
            'agents.consumers.generate_voice_conversation_response',
            return_value=(streamed_response, 'deterministic_fallback'),
        ), patch(
            'agents.consumers.synthesize_tts',
            return_value=(b'fake-realtime-tts', 'audio/mpeg'),
        ):
            async def scenario():
                communicator = self._communicator(
                    f'/ws/voice-conversation/sessions/{self.session.id}/',
                    session_cookie=owner_cookie,
                )
                connected, _ = await communicator.connect()
                self.assertTrue(connected)
                await communicator.receive_json_from()
                await communicator.receive_json_from()

                await communicator.send_json_to(
                    {
                        'type': 'audio_chunk',
                        'event_id': 'chunk-old-turn-1',
                        'chunk_id': 'chunk-old-turn-1',
                        'sequence': 1,
                        'mime_type': 'audio/webm',
                        'size_bytes': 3,
                        'duration_ms': 1000,
                        'is_final': True,
                        'audio_base64': 'AQID',
                    }
                )

                while True:
                    event = await communicator.receive_json_from()
                    if event['type'] == 'realtime_turn_persisted':
                        persisted_turn_event = event
                    elif event['type'] == 'tts_audio_complete':
                        old_tts_complete_event = event
                        break

                await communicator.send_json_to(
                    {
                        'type': 'audio_chunk',
                        'event_id': 'chunk-new-turn-1',
                        'chunk_id': 'chunk-new-turn-1',
                        'sequence': 2,
                        'mime_type': 'audio/webm',
                        'size_bytes': 3,
                        'duration_ms': 1000,
                        'is_final': False,
                        'audio_base64': 'AQID',
                    }
                )

                new_ack_event = await communicator.receive_json_from()
                interrupt_event = await communicator.receive_json_from()
                interrupted_turn_event = await communicator.receive_json_from()
                new_partial_event = await communicator.receive_json_from()

                self.assertEqual(new_ack_event['type'], 'audio_chunk_ack')
                self.assertEqual(new_ack_event['sequence'], 2)
                self.assertEqual(interrupt_event['type'], 'assistant_interrupted')
                self.assertEqual(interrupt_event['response_id'], old_tts_complete_event['response_id'])
                self.assertEqual(interrupt_event['trigger'], 'learner_audio')
                self.assertEqual(interrupt_event['previous_state'], 'awaiting_playback_completion')
                self.assertTrue(interrupt_event['had_active_response'])
                self.assertEqual(persisted_turn_event['type'], 'realtime_turn_persisted')
                self.assertEqual(
                    interrupted_turn_event['type'],
                    'realtime_turn_interrupted',
                )
                self.assertTrue(interrupted_turn_event['turn']['metadata']['interrupted'])
                self.assertEqual(
                    interrupted_turn_event['turn']['metadata']['interruption_trigger'],
                    'learner_audio',
                )
                self.assertEqual(new_partial_event['type'], 'transcript_partial')
                self.assertEqual(new_partial_event['transcript'], 'hello teacher')

                await communicator.disconnect()

            async_to_sync(scenario)()
        self.assertEqual(
            session_holder['session'].sent_chunks,
            [(b'\x01\x02\x03', True), (b'\x01\x02\x03', False)],
        )
        saved_turn = VoiceConversationTurn.objects.get()
        self.assertTrue(saved_turn.metadata['interrupted'])
        self.assertEqual(saved_turn.metadata['interruption_trigger'], 'learner_audio')

    @patch(
        'agents.consumers.create_realtime_stt_session',
        side_effect=RealtimeSttConfigError('Realtime speech-to-text is not configured yet.'),
    )
    def test_unavailable_stt_provider_emits_unavailable_status(
        self,
        create_realtime_stt_session,
    ):
        owner_cookie = self._session_cookie(self.user)

        async def scenario():
            communicator = self._communicator(
                f'/ws/voice-conversation/sessions/{self.session.id}/',
                session_cookie=owner_cookie,
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.receive_json_from()
            await communicator.receive_json_from()

            await communicator.send_json_to(
                {
                    'type': 'audio_chunk',
                    'event_id': 'chunk-3',
                    'chunk_id': 'chunk-3',
                    'sequence': 3,
                    'mime_type': 'audio/webm',
                    'size_bytes': 3,
                    'duration_ms': 1000,
                    'is_final': False,
                    'audio_base64': 'AQID',
                }
            )

            ack_event = await communicator.receive_json_from()
            stt_status_event = await communicator.receive_json_from()

            self.assertEqual(ack_event['type'], 'audio_chunk_ack')
            self.assertEqual(stt_status_event['type'], 'stt_status')
            self.assertEqual(stt_status_event['state'], 'unavailable')
            self.assertEqual(
                stt_status_event['message'],
                (
                    'Realtime speech-to-text is unavailable. '
                    'Use the standard voice turn flow for this session.'
                ),
            )

            await communicator.disconnect()

        async_to_sync(scenario)()
        self.assertTrue(create_realtime_stt_session.called)

    def test_invalid_audio_payload_is_rejected(self):
        owner_cookie = self._session_cookie(self.user)

        async def scenario():
            communicator = self._communicator(
                f'/ws/voice-conversation/sessions/{self.session.id}/',
                session_cookie=owner_cookie,
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.receive_json_from()
            await communicator.receive_json_from()

            await communicator.send_json_to(
                {
                    'type': 'audio_chunk',
                    'event_id': 'chunk-2',
                    'chunk_id': 'chunk-2',
                    'sequence': 2,
                    'mime_type': 'audio/webm',
                    'size_bytes': 4,
                    'duration_ms': 250,
                    'audio_base64': 'not-base64',
                }
            )
            error_event = await communicator.receive_json_from()
            self.assertEqual(error_event['type'], 'error')
            self.assertEqual(error_event['code'], 'invalid_payload')
            self.assertEqual(error_event['event_id'], 'chunk-2')
            self.assertEqual(error_event['for_type'], 'audio_chunk')

            await communicator.disconnect()

        async_to_sync(scenario)()

    @override_settings(VOICE_CONVERSATION_REALTIME_MAX_EVENTS_PER_MINUTE=1)
    def test_realtime_rate_limit_closes_noisy_clients(self):
        owner_cookie = self._session_cookie(self.user)

        async def scenario():
            communicator = self._communicator(
                f'/ws/voice-conversation/sessions/{self.session.id}/',
                session_cookie=owner_cookie,
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.receive_json_from()
            await communicator.receive_json_from()

            await communicator.send_json_to({'type': 'ping', 'event_id': 'ping-1'})
            first_pong = await communicator.receive_json_from()
            self.assertEqual(first_pong['type'], 'pong')

            await communicator.send_json_to({'type': 'ping', 'event_id': 'ping-2'})
            error_event = await communicator.receive_json_from()
            self.assertEqual(error_event['type'], 'error')
            self.assertEqual(error_event['code'], 'rate_limited')
            self.assertEqual(error_event['for_type'], 'ping')

            await communicator.wait()

        async_to_sync(scenario)()
