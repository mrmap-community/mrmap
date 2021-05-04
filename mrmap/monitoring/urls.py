from django.urls import path

from monitoring.views import MonitoringRunTableView, MonitoringResultTableView, MonitoringRunNewView, \
    MonitoringResultDetailView, HealthStateTableView, HealthStateDetailView

app_name = 'monitoring'
urlpatterns = [
    # MonitoringRuns
    path('runs', MonitoringRunTableView.as_view(), name='run_overview'),
    path('runs/new', MonitoringRunNewView.as_view(), name='run_new'),

    # MonitoringResults
    path('results', MonitoringResultTableView.as_view(), name='result_overview'),
    path('results/<pk>', MonitoringResultDetailView.as_view(), name='result_details'),

    # HealthStates
    path('health-states', HealthStateTableView.as_view(), name='health_state_overview'),
    path('health-states/<pk>', HealthStateDetailView.as_view(), name='health_state_details'),
]

