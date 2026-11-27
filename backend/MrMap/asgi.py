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

# The telemetry of the websocket tier is initialized once, in the process this
# file is imported into - which is one uvicorn worker per Gunicorn worker, never
# a master (the ASGI server is deliberately never preloaded, #1617). The lifecycle
# creates nothing at all while ``MRMAP_OTEL_MODE`` is off (#1779).
from MrMap.telemetry import lifecycle  # noqa E402

_telemetry = lifecycle.initialize_for_process(role=lifecycle.ROLE_WS)

if _telemetry is not None:
    # An open websocket is not an HTTP request, so upstream has nothing to
    # instrument there and none is pretended at. What the ``http`` branch of this
    # router does get is the upstream ASGI instrumentation: it creates the server
    # span and asks the global propagator - MrMap's own - for the parent, so the
    # public-ingress rule of propagation.py holds on this path too. The
    # ``DjangoInstrumentor`` is deliberately not installed in this process: both
    # of them on one request would be the double instrumentation ADR-0003 rules
    # out, and the ASGI middleware sees every request of this entry point.
    from opentelemetry.instrumentation.asgi import \
        OpenTelemetryMiddleware  # noqa E402

    asgi_app = OpenTelemetryMiddleware(asgi_app)

application = ProtocolTypeRouter({
    # Django's ASGI application to handle traditional HTTP requests
    "http": asgi_app,

    "websocket": AllowedHostsOriginValidator(token_auth_middleware_stack(
        URLRouter(
            notify.routing.websocket_urlpatterns,
        )
    ),),
})
