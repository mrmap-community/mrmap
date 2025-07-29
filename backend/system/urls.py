from django.urls import path
from rest_framework_extensions.routers import ExtendedSimpleRouter
from system import views

app_name = 'system'

router = ExtendedSimpleRouter(trailing_slash=False)
(
    router.register(r'crontabs', views.CrontabScheduleViewSet,
                    basename='crontab'),
    router.register(r'periodic-tasks', views.PeriodicTaskViewSet,
                    basename='periodictask')

)

urlpatterns = router.urls + [

    path(
        route=r'info',
        view=views.SystemView.as_view(),
        name='system-info'
    ),


]
