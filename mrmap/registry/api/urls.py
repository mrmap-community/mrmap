from rest_framework.routers import DefaultRouter
from registry.api.views import mapcontext as mapcontext_views
from registry.api.views import metadata as metadata_views
from registry.api.views import service as service_views

app_name = 'registry'

registry_api_router = DefaultRouter()

# Services
registry_api_router.register(app_name + '/service/services', service_views.ServiceViewSet, basename='service')
registry_api_router.register(app_name + '/service/layers', service_views.LayerViewSet, basename='layer')
registry_api_router.register(app_name + '/service/featuretypes', service_views.FeatureTypeViewSet, basename='feature_type')
# Metadata
registry_api_router.register(app_name + '/metadata/datasets', metadata_views.DatasetMetadataViewSet, basename='dataset_metadata')
# Map Context
registry_api_router.register(app_name + '/mapcontexts', mapcontext_views.MapContextViewSet, basename='mapcontext')
