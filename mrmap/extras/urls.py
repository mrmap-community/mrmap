from extras.viewsets import CrontabScheduleViewSet
from rest_framework_extensions.routers import ExtendedSimpleRouter

app_name = 'beat'

router = ExtendedSimpleRouter(trailing_slash=False)
(
    router.register(r'crontab', CrontabScheduleViewSet, basename='crontab')
)

urlpatterns = router.urls
