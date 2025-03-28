from notify import views
from rest_framework_extensions.routers import ExtendedSimpleRouter

app_name = 'notify'

router = ExtendedSimpleRouter(trailing_slash=False)
(
    # jobs
    router.register(r'task-results',
                    views.TaskResultReadOnlyViewSet, basename='taskresult'),

    # background prcesses
    router.register(r'background-processes',
                    views.BackgroundProcessViewSet, basename='backgroundprocess')
    .register(r'logs', views.NestedBackgroundProcessLogViewSet, basename='backgroundprocess-logs', parents_query_lookups=['background_process']),
    router.register(r'background-processes',
                    views.BackgroundProcessViewSet, basename='backgroundprocess')
    .register(r'threads', views.NestedTaskResultReadOnlyViewSet, basename='backgroundprocess-threads', parents_query_lookups=['process']),

    router.register(r'background-processes-log',
                    views.BackgroundProcessLogViewSet, basename='backgroundprocesslog'),

)

urlpatterns = router.urls
