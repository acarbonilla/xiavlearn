from django.urls import path

from .consumers import VoiceConversationSessionConsumer


websocket_urlpatterns = [
    path(
        'ws/voice-conversation/sessions/<int:session_id>/',
        VoiceConversationSessionConsumer.as_asgi(),
    ),
]
