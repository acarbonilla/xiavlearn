from channels.routing import URLRouter

from agents.routing import websocket_urlpatterns


application = URLRouter(websocket_urlpatterns)
