"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 15.08.19

"""

from django.urls import path, include


# Routers provide an easy way of automatically determining the URL conf.
from rest_framework import routers

from api.views import ServiceViewSet, LayerViewSet, OrganizationViewSet, GroupViewSet, RoleViewSet, MetadataViewSet

router = routers.DefaultRouter()
router.register('organizations', OrganizationViewSet, basename="organization")
router.register('metadata', MetadataViewSet, basename="metadata")
router.register('services', ServiceViewSet, basename="service")
router.register('layers', LayerViewSet, basename="layer")
router.register('groups', GroupViewSet, basename="group")
router.register('role', RoleViewSet, basename="role")


urlpatterns = [
    path("", include(router.urls)),
]