from rest_framework.routers import DefaultRouter
from registry.api.views.mapcontext import MapContextViewSet
from registry.api.views.metadata import DatasetMetadataViewSet
from registry.api.views.service import ServiceViewSet, FeatureTypeViewSet, LayerViewSet

app_name = 'registry'

registry_api_router = DefaultRouter(trailing_slash=False)

# Services
registry_api_router.register(app_name + '/services', ServiceViewSet, basename='services_api_router')
registry_api_router.register(app_name + '/layers', LayerViewSet, basename='layer_api_router')
registry_api_router.register(app_name + '/feature_types', FeatureTypeViewSet, basename='feature_types_api_router')
# Metadata
registry_api_router.register(app_name + '/dataset_metadata', DatasetMetadataViewSet, basename='dataset_metadata_api_router')
# Map Context
registry_api_router.register(app_name + '/mapcontexts', MapContextViewSet, basename='mapcontext_api_router')
