from django.db.models import Count

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .models import VoiceConversationSession


class VoiceConversationSessionConsumer(AsyncJsonWebsocketConsumer):
    CLOSE_CODE_UNAUTHENTICATED = 4401
    CLOSE_CODE_NOT_FOUND = 4404

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
        self.group_name = f'voice-conversation-session-{self.session_id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json(
            {
                'type': 'connected',
                'session_id': self.session_id,
                'message': 'Realtime voice conversation socket connected.',
            }
        )
        await self.send_json(self._build_session_status_event(session))

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        message_type = content.get('type')

        if message_type == 'heartbeat':
            await self.send_json(
                {
                    'type': 'heartbeat',
                    'session_id': self.session_id,
                    'status': 'ok',
                }
            )
            return

        if message_type == 'session_status':
            session = await self._get_owned_session(self.session_id, self.scope['user'].id)
            if session is None:
                await self.send_json(
                    {
                        'type': 'error',
                        'code': 'session_not_found',
                        'message': 'Voice conversation session not found.',
                    }
                )
                return
            self.session_snapshot = session
            await self.send_json(self._build_session_status_event(session))
            return

        if message_type == 'echo':
            await self.send_json(
                {
                    'type': 'echo',
                    'session_id': self.session_id,
                    'payload': content.get('payload', {}),
                }
            )
            return

        await self.send_json(
            {
                'type': 'error',
                'code': 'unsupported_message',
                'message': 'Unsupported realtime message type.',
            }
        )

    @staticmethod
    def _build_session_status_event(session):
        return {
            'type': 'session_status',
            'session': {
                'id': session['id'],
                'status': session['status'],
                'target_skill': session['target_skill'],
                'cefr_level': session['cefr_level'],
                'turn_count': session['turn_count'],
                'practice_only': True,
                'realtime_stage': 'skeleton',
            },
        }

    @database_sync_to_async
    def _get_owned_session(self, session_id, user_id):
        session = (
            VoiceConversationSession.objects.filter(pk=session_id, user_id=user_id)
            .annotate(turn_count=Count('turns'))
            .values('id', 'status', 'target_skill', 'cefr_level', 'turn_count')
            .first()
        )
        return session
