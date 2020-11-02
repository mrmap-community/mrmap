"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 27.10.20

"""
from django.urls import path

from . import views

urlpatterns = [
    # path('/<int:run_id>', views.check, name='check'),
    path('internal/<str:metadata_id>/<int:config_id>', views.check_internal, name='check_internal'),
]
