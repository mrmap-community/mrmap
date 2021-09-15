from django.urls import path

from monitoring.views import MonitoringRunTableView, MonitoringResultTableView, MonitoringRunNewView, \
    MonitoringResultDetailView, HealthStateTableView, HealthStateDetailView

app_name = 'monitoring'
urlpatterns = [
    # MonitoringRuns
    path('runs', MonitoringRunTableView.as_view(), name='monitoring_run_list'),
    path('runs/create', MonitoringRunNewView.as_view(), name='monitoring_run_add'),

    # MonitoringResults
    path('results', MonitoringResultTableView.as_view(), name='monitoring_result_list'),
    path('results/<pk>', MonitoringResultDetailView.as_view(), name='monitoring_result_view'),

    # HealthStates
    path('health-states', HealthStateTableView.as_view(), name='health_state_list'),
    path('health-states/<pk>', HealthStateDetailView.as_view(), name='health_state_view'),
]
