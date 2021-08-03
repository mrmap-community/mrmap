"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 27.10.20

"""
from django.urls import path

from .views import ConformityCheckRunCreateView, ConformityCheckRunListView, \
    ConformityCheckRunDeleteView, ConformityCheckRunReportView

app_name = 'quality'
urlpatterns = [
    path("runs", ConformityCheckRunListView.as_view(), name='conformity_check_run_list'),
    path('runs/create', ConformityCheckRunCreateView.as_view(), name='conformity_check_run_add'),
    path('runs/<pk>/delete', ConformityCheckRunDeleteView.as_view(), name='conformity_check_run_delete'),
    path('runs/<pk>/report', ConformityCheckRunReportView.as_view(), name='conformity_check_run_report'),
]
