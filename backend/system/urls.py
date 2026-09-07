from django.urls import path
from system import views

from extras.routers import NestedDefaultRouter

app_name = 'system'


router = NestedDefaultRouter(trailing_slash=False)

router.register(r'crontabs', views.CrontabScheduleViewSet,
                basename='crontab')
router.register(r'periodic-tasks', views.PeriodicTaskViewSet,
                basename='periodictask')

urlpatterns = router.urls + [
    path(
        route=r'info',
        view=views.SystemView.as_view(),
        name='system-info'
    ),
]
