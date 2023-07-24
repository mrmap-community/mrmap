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
                    views.BackgroundProcessViewSet, basename='backgroundprocess'),
)

urlpatterns = router.urls
