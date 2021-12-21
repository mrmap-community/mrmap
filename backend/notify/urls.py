from rest_framework_extensions.routers import ExtendedSimpleRouter

from notify import views

app_name = 'notify'

nested_api_router = ExtendedSimpleRouter()
(
    # jobs
    nested_api_router.register(
        r'task-results', views.TaskResultReadOnlyViewSet, basename='taskresult')
)

urlpatterns = nested_api_router.urls
