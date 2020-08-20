from django.urls import path

from monitoring.views import call_run_monitoring

app_name = 'monitoring'
urlpatterns = [
    path('run-monitoring/<metadata_id>', call_run_monitoring, name='run-monitoring'),
]

