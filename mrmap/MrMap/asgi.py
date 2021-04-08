import os
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.core.asgi import get_asgi_application

import websockets.routing


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MrMap.settings')
django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
  # Django's ASGI application to handle traditional HTTP requests
  "http": django_asgi_app,

  "websocket": AuthMiddlewareStack(
      URLRouter(
          websockets.routing.websocket_urlpatterns,
      )
  ),
})
