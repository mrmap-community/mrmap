"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 27.10.20

"""
from django.urls import path

from .views import ConformityCheckRunCreateView, ConformityCheckRunListView

app_name = 'quality'
urlpatterns = [
    path("runs", ConformityCheckRunListView.as_view(), name='conformity_check_run_list'),
    path('runs/create', ConformityCheckRunCreateView.as_view(), name='conformity_check_run_add'),
    path('runs/<pk>/delete', ConformityCheckRunCreateView.as_view(), name='conformity_check_run_delete'),
    # path('<str:metadata_id>/latest', views.get_latest, name='latest'),
]
