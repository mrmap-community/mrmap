from django.urls import path
from extras.routers import NestedDefaultRouter
from notify import views

app_name = 'notify'

router = NestedDefaultRouter(trailing_slash=False)
background_process_routes = router.register(
    r'background-processes', views.BackgroundProcessViewSet, basename='backgroundprocess')
background_process_routes.register(r'logs', views.NestedBackgroundProcessLogViewSet,
                                   basename='backgroundprocess-logs', parents_query_lookups=['background_process'])
# the nested `threads` route which listed the `TaskResult` rows of a process
# is retired with the `threads` relation itself; D01/B of #1175 decided the
# breaking cutover, so no nested replacement is announced (#1179)

# the top level `task-results` route which answered the legacy `TaskResult`
# rows is retired with the D01/B cutover: the announcement named this release,
# so no read-only replacement for historical rows is offered (#1180)

# background prcesses
router.register(r'background-processes-log',
                views.BackgroundProcessLogViewSet, basename='backgroundprocesslog')

# the persisted incidents of the deployment (#1319): the read-only api of the
# OperationalIncident which publishers of #1320 report and the notification
# center of #1321 reads
router.register(
    r'operational-incidents',
    views.OperationalIncidentViewSet,
    basename='operationalincident')

urlpatterns = [
    # the one-time credential of a WebSocket handshake (#1472): a client whose
    # identity is a knox token mints a ticket here instead of putting that token
    # into the URL of the handshake, where the proxy access log would keep it
    path('websocket-ticket', views.WebsocketTicketView.as_view(),
         name='websocket-ticket'),
] + router.urls
