import os

from channels.security.websocket import AllowedHostsOriginValidator
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter
from django.core.asgi import get_asgi_application

from xiavlearn.routing import application as websocket_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'xiavlearn.settings')

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter(
    {
        'http': django_asgi_app,
        'websocket': AllowedHostsOriginValidator(
            AuthMiddlewareStack(websocket_application)
        ),
    }
)
