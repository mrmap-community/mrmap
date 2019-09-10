"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 15.08.19

"""

from django.urls import path, include


# Routers provide an easy way of automatically determining the URL conf.
from rest_framework import routers

from api.views import ServiceViewSet, LayerViewSet, OrganizationViewSet

router = routers.DefaultRouter()
router.register('services', ServiceViewSet, basename="Service")
router.register('layers', LayerViewSet, basename="Layer")
router.register('organizations', OrganizationViewSet, basename="Organization")


urlpatterns = [
    path("", include(router.urls)),
]