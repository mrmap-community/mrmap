"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 15.08.19

"""

from django.urls import path, include


# Routers provide an easy way of automatically determining the URL conf.
from rest_framework import routers

from api.views import *

router = routers.DefaultRouter()

app_name = "api"
urlpatterns = [
    path("", include(router.urls)),
    path("menu", menu_view, name="menu"),
    path("generate-token", generate_token, name="generate-token"),
]
