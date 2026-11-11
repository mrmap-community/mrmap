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

urlpatterns = router.urls
