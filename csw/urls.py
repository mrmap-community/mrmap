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
    path('', resolve_request, name='resolve-request'),
]
