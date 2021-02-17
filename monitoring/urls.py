from django.urls import path

from monitoring.views import MonitoringRunTableView, MonitoringResultTableView, MonitoringRunNewView

app_name = 'monitoring'
urlpatterns = [
    # MonitoringRuns
    path('runs', MonitoringRunTableView.as_view(), name='run_overview'),
    path('runs/new', MonitoringRunNewView.as_view(), name='run_new'),

    # MonitoringResults
    path('results', MonitoringResultTableView.as_view(), name='result_overview'),

    # HealthStates
    path('health-states', MonitoringRunTableView.as_view(), name='health-state'),
]

