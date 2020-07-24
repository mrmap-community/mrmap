"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 05.05.20

"""
from django.urls import path

from csw.views import *

app_name = 'csw'
urlpatterns = [
    path('', get_csw_results, name='get-csw-results'),
    path('harvest/<metadata_id>', harvest_catalogue, name='harvest-catalogue'),
]
