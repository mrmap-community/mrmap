import os

from django.core.asgi import get_asgi_application

# Fetch Django ASGI application early to ensure AppRegistry is populated
# before importing consumers and AuthMiddlewareStack that may import ORM
# models.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MrMap.settings')
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter # noqa
from channels.auth import AuthMiddlewareStack # noqa
import websockets.routing # noqa
from channels.security.websocket import AllowedHostsOriginValidator # noqa


application = ProtocolTypeRouter({
  # Django's ASGI application to handle traditional HTTP requests
  "http": django_asgi_app,

  "websocket": AllowedHostsOriginValidator(AuthMiddlewareStack(
      URLRouter(
          websockets.routing.websocket_urlpatterns,
      )
  ),),
})
