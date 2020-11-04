"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 27.10.20

"""
from django.urls import path

from . import views

urlpatterns = [
    path('<str:metadata_id>', views.validate, name='check'),
    path('<int:config_id>/<str:metadata_id>', views.check, name='check'),
    path('internal/<str:metadata_id>/<int:config_id>', views.new_check,
         name='check_internal'),
    path('configs/<str:metadata_type>', views.get_configs_for,
         name='get_configs'),
]
