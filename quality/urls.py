"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 27.10.20

"""
from django.urls import path

from . import views

app_name = 'quality'
urlpatterns = [
    path('<str:metadata_id>', views.validate, name='check'),
    path('<str:metadata_id>/latest', views.get_latest, name='latest'),
]
