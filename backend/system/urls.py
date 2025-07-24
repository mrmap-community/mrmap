from rest_framework_extensions.routers import ExtendedSimpleRouter
from system.views import CrontabScheduleViewSet

app_name = 'system'

router = ExtendedSimpleRouter(trailing_slash=False)
(
    router.register(r'crontabs', CrontabScheduleViewSet, basename='crontab')
)

urlpatterns = router.urls
