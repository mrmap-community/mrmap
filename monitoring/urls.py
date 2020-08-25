from django.urls import path

from monitoring.views import call_run_monitoring, monitoring_results

app_name = 'monitoring'
urlpatterns = [
    path('run-monitoring/<metadata_id>', call_run_monitoring, name='run-monitoring'),
    path('health-state/<metadata_id>/', monitoring_results, name='health-state'),
    path('health-state/<metadata_id>/<monitoring_run_id>', monitoring_results, name='health-state-specific'),
]

