from importlib import import_module
from uuid import uuid4

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.contrib.auth import (
    BACKEND_SESSION_KEY,
    HASH_SESSION_KEY,
    SESSION_KEY,
)
from django.contrib.auth.models import User
from django.test import TransactionTestCase

from agents.models import VoiceConversationSession, VoiceConversationTurn
from xiavlearn.asgi import application


class VoiceConversationRealtimeTests(TransactionTestCase):
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

    def _communicator(self, path, session_cookie=None):
        headers = []
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
            self.assertEqual(status_event['type'], 'session_status')
            self.assertEqual(status_event['session']['id'], self.session.id)
            self.assertEqual(status_event['session']['status'], 'active')
            self.assertEqual(status_event['session']['target_skill'], 'speaking')
            self.assertEqual(status_event['session']['turn_count'], 1)
            self.assertTrue(status_event['session']['practice_only'])
            self.assertEqual(status_event['session']['realtime_stage'], 'skeleton')

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

    def test_heartbeat_echo_and_status_messages_work(self):
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

            await communicator.send_json_to({'type': 'heartbeat'})
            heartbeat_event = await communicator.receive_json_from()
            self.assertEqual(
                heartbeat_event,
                {
                    'type': 'heartbeat',
                    'session_id': self.session.id,
                    'status': 'ok',
                },
            )

            await communicator.send_json_to(
                {'type': 'echo', 'payload': {'debug': True, 'step': 'skeleton'}}
            )
            echo_event = await communicator.receive_json_from()
            self.assertEqual(echo_event['type'], 'echo')
            self.assertEqual(echo_event['session_id'], self.session.id)
            self.assertEqual(
                echo_event['payload'],
                {'debug': True, 'step': 'skeleton'},
            )

            await communicator.send_json_to({'type': 'session_status'})
            status_event = await communicator.receive_json_from()
            self.assertEqual(status_event['type'], 'session_status')
            self.assertEqual(status_event['session']['turn_count'], 0)

            await communicator.send_json_to({'type': 'unsupported'})
            error_event = await communicator.receive_json_from()
            self.assertEqual(error_event['type'], 'error')
            self.assertEqual(error_event['code'], 'unsupported_message')

            await communicator.disconnect()

        async_to_sync(scenario)()
