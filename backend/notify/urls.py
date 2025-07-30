from notify import views
from rest_framework_extensions.routers import ExtendedSimpleRouter

app_name = 'notify'

router = ExtendedSimpleRouter(trailing_slash=False)
background_process_routes = router.register(
    r'background-processes', views.BackgroundProcessViewSet, basename='backgroundprocess')
background_process_routes.register(r'logs', views.NestedBackgroundProcessLogViewSet,
                                   basename='backgroundprocess-logs', parents_query_lookups=['background_process'])
background_process_routes.register(r'threads', views.NestedTaskResultReadOnlyViewSet,
                                   basename='backgroundprocess-threads', parents_query_lookups=['process'])
(
    # jobs
    router.register(r'task-results',
                    views.TaskResultReadOnlyViewSet, basename='taskresult'),

    # background prcesses
    background_process_routes,

    router.register(r'background-processes-log',
                    views.BackgroundProcessLogViewSet, basename='backgroundprocesslog'),

)

urlpatterns = router.urls
