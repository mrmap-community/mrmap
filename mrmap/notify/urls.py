from rest_framework_extensions.routers import ExtendedSimpleRouter

from notify import views

app_name = 'notify'

router = ExtendedSimpleRouter()
(
    # jobs
    router.register(r'task-results', views.TaskResultReadOnlyViewSet, basename='taskresult'),

    # background prcesses
    router.register(r'background-processes', views.BackgroundProcessViewSet, basename='backgroundprocess'),
)

urlpatterns = router.urls
