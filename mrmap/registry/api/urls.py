from rest_framework.routers import DefaultRouter
from registry.api.views import mapcontext as mapcontext_views
from registry.api.views import metadata as metadata_views
from registry.api.views import service as service_views

app_name = 'registry'

registry_api_router = DefaultRouter(trailing_slash=False)

# Services
registry_api_router.register(app_name + '/services', service_views.ServiceViewSet, basename='service')
registry_api_router.register(app_name + '/layers', service_views.LayerViewSet, basename='layer')
registry_api_router.register(app_name + '/feature-types', service_views.FeatureTypeViewSet, basename='feature_type')
# Metadata
registry_api_router.register(app_name + '/dataset-metadata', metadata_views.DatasetMetadataViewSet, basename='dataset_metadata')
# Map Context
registry_api_router.register(app_name + '/mapcontexts', mapcontext_views.MapContextViewSet, basename='mapcontext')
