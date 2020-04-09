"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 15.08.19

"""

from django.urls import path, include


# Routers provide an easy way of automatically determining the URL conf.
from rest_framework import routers

from api.views import ServiceViewSet, LayerViewSet, OrganizationViewSet, GroupViewSet, RoleViewSet, MetadataViewSet, \
    CatalogueViewSet, menu_view, generate_token

router = routers.DefaultRouter()
# catalogue api
router.register('catalogue', CatalogueViewSet, basename="catalogue")
# modular parts of api
router.register('organization', OrganizationViewSet, basename="organization")
router.register('metadata', MetadataViewSet, basename="metadata")
router.register('service', ServiceViewSet, basename="service")
router.register('layer', LayerViewSet, basename="layer")
router.register('group', GroupViewSet, basename="group")
#router.register('role', RoleViewSet, basename="role")

app_name = "api"
urlpatterns = [
    path("", include(router.urls)),
    path("menu", menu_view, name="menu"),
    path("generate-token", generate_token, name="generate-token"),
]