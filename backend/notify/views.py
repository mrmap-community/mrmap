from extras.viewsets import NestedModelViewSet
from notify.filters import (BackgroundProcessFilterSet,
                            OperationalIncidentFilterSet)
from notify.models import (BackgroundProcess, BackgroundProcessLog,
                           OperationalIncident)
from notify.permissions import CanChangeRelatedResource
from notify.serializers import (
    BackgroundProcessLogSerializer, BackgroundProcessSerializer,
    OperationalIncidentSerializer)
from notify.ws_ticket import TICKET_TTL_SECONDS, mint_ticket
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_json_api.views import ModelViewSet, ReadOnlyModelViewSet


class BackgroundProcessViewSetMixin(

):
    queryset = BackgroundProcess.objects.process_info()
    serializer_class = BackgroundProcessSerializer
    filterset_class = BackgroundProcessFilterSet
    permission_classes = [CanChangeRelatedResource]
    # the progress of process_info() is a plain annotation of the queryset, so
    # the overview can order its rows by the percentage it renders (#1035);
    # the state of #1207 is its other annotation and the revision its column
    ordering_fields = [
        "id",
        "date_created",
        "progress",
        "state",
        "revision",
    ]

    def get_queryset(self):
        """Answer only the processes which belong to resources the user may see.

        A process names its resource with a generic relation, so what the user is
        permitted to see has to be looked up per type of the related resource.
        Anonymous clients read this endpoint like every other read only endpoint
        of the api and a superuser sees every process, so neither of them needs
        the lookup.
        """
        queryset = super().get_queryset()
        user = getattr(self.request, 'user', None)
        if user is None or not user.is_authenticated or user.is_superuser:
            return queryset
        return BackgroundProcess.objects.visible_for_user(
            user, queryset=queryset)


class BackgroundProcessViewSet(
    BackgroundProcessViewSetMixin,
    ModelViewSet
):
    pass


class BackgroundProcessLogViewSetMixin(

):
    queryset = BackgroundProcessLog.objects.all()
    serializer_class = BackgroundProcessLogSerializer
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        "log_type": ["exact", "icontains", "contains"],
        "description": ["exact", "icontains", "contains"],
        "date": ["exact", "icontains", "contains"],
        # a log line is the error detail of its process, and the history asks
        # of one process which errors it left behind (#1208)
        "background_process": ["exact", "in"],
    }
    ordering_fields = [
        "id",
        "date",
    ]

    def get_queryset(self):
        """Answer only the log entries of processes the user may see.

        A log entry carries the error detail of the work done on a resource,
        so it belongs to whoever is permitted to read the process which
        reports that work - reading the errors of a hidden service must not
        be easier than reading the service itself. As with the processes,
        anonymous clients and a superuser read this endpoint as its queryset
        already says.
        """
        queryset = super().get_queryset()
        user = getattr(self.request, 'user', None)
        if user is None or not user.is_authenticated or user.is_superuser:
            return queryset
        return queryset.filter(background_process__in=BackgroundProcess.objects.visible_for_user(
            user).values("pk"))


class BackgroundProcessLogViewSet(
    BackgroundProcessLogViewSetMixin,
    ReadOnlyModelViewSet
):
    pass


class NestedBackgroundProcessLogViewSet(
    BackgroundProcessLogViewSetMixin,
    NestedModelViewSet
):
    pass


class OperationalIncidentViewSet(
    ReadOnlyModelViewSet
):
    """The incidents of the deployment which the caller may view (#1319).

    Read-only for regular clients: an incident is the persisted report of
    what its publishers decided, and those publishers are the watchdogs and
    task reporters of #1320, never a client of this api. The endpoint is no
    second status engine - the background process, the job and the service
    alerts behind an incident stay authoritative for the state of the work.

    The one permission rule is the narrowing of ``visible_for_user``, which
    every read of this viewset runs over: an incident of a resource the
    caller may view, and system incidents for a superuser alone. Anonymous
    clients are refused the endpoint entirely, so neither a list, nor a
    count, nor a filter, nor the answer behind a detail url can tell an
    unauthorized caller about an incident he may not see.
    """

    queryset = OperationalIncident.objects.all()
    serializer_class = OperationalIncidentSerializer
    filterset_class = OperationalIncidentFilterSet
    permission_classes = [IsAuthenticated]
    # the list of the notification center orders its rows by the moment of
    # the last report; the history asks the resolved ones by theirs
    ordering_fields = [
        "id",
        "severity",
        "occurrence_count",
        "first_occurred_at",
        "last_occurred_at",
        "resolved_at",
    ]
    # reading only: an incident is decided by its publishers, never by a
    # client of this endpoint
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        """Answer only the incidents which the caller may view.

        The narrowing of ``visible_for_user`` is the single rule behind list,
        detail, every filter and every count of this endpoint; a superuser
        needs no lookup and an anonymous request never reaches this point,
        the permission class refuses it before.
        """
        queryset = super().get_queryset()
        if getattr(self, 'swagger_fake_view', False):
            return queryset
        return OperationalIncident.objects.visible_for_user(
            getattr(self.request, 'user', None), queryset=queryset)


class WebsocketTicketView(APIView):
    """Mint the one-time credential of one WebSocket handshake (#1472).

    ``POST /api/notify/websocket-ticket`` answers ``{"ticket": ..., "expires_in":
    10}`` for the authenticated caller. It exists for the clients whose identity
    is a knox token rather than a browser session - those previously opened
    ``/ws/default/?token=<knox token>``, which wrote a credential valid for
    ``REST_KNOX["TOKEN_TTL"]`` into every proxy access log which records the URL.
    What that log keeps now is a random value which the very next handshake burns
    and which expires unspent after ten seconds (``notify/ws_ticket.py``).

    Authentication is the plain API stack, so the caller proves itself here with
    the credential it already has - ``Authorization: Token ...`` for a machine
    client, the session cookie (and its CSRF header) for a browser. The ticket
    inherits nothing: it names no user, and a refused request answers nothing.

    Answering plain JSON instead of the JSON:API envelope follows the auth
    endpoints of ``accounts/views/auth.py``: the payload is not a resource, and a
    client fetching a ticket is booting a socket, not reading the registry.
    """

    renderer_classes = [JSONRenderer]
    permission_classes = [IsAuthenticated]
    # minting is the only verb; a ticket is never read back, refreshed or revoked
    http_method_names = ["post"]

    def post(self, request):
        return Response({
            "ticket": mint_ticket(request.user.pk),
            "expires_in": TICKET_TTL_SECONDS,
        })
