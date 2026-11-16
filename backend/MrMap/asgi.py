import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MrMap.settings')

# Fetch Django ASGI application early to ensure AppRegistry is populated
# before importing consumers and the auth middleware stack that may import ORM
# models.
from django.core.asgi import get_asgi_application  # noqa E402

asgi_app = get_asgi_application()


import notify.routing  # noqa E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa E402
from channels.security.websocket import \
    AllowedHostsOriginValidator  # noqa E402
from notify.auth import token_auth_middleware_stack  # noqa E402

application = ProtocolTypeRouter({
    # Django's ASGI application to handle traditional HTTP requests
    "http": asgi_app,

    "websocket": AllowedHostsOriginValidator(token_auth_middleware_stack(
        URLRouter(
            notify.routing.websocket_urlpatterns,
        )
    ),),
})
