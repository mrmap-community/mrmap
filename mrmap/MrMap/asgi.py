import os

import django
from channels.http import AsgiHandler
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import websockets.routing


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MrMap.settings')
django.setup()

application = ProtocolTypeRouter({
  "http": AsgiHandler(),

  "websocket": AuthMiddlewareStack(
      URLRouter(
          websockets.routing.websocket_urlpatterns,
      )
  ),
})
