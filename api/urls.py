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
# catalogue api
router.register('catalogue', CatalogueViewSet, basename="catalogue")
router.register('suggestion', SuggestionViewSet, basename="suggestion")
router.register('category', CategoryViewSet, basename="category")
# modular parts of api
router.register('organization', OrganizationViewSet, basename="organization")
router.register('pending-task', PendingTaskViewSet, basename="pending-task")
router.register('metadata', MetadataViewSet, basename="metadata")
router.register('service', ServiceViewSet, basename="service")
router.register('layer', LayerViewSet, basename="layer")
router.register('group', GroupViewSet, basename="group")

app_name = "api"
urlpatterns = [
    path("", include(router.urls)),
    path("menu", menu_view, name="menu"),
    path("generate-token", generate_token, name="generate-token"),
]