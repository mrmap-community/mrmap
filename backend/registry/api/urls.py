from registry.api.views import mapcontext as mapcontext_views
from registry.api.views import metadata as metadata_views
from registry.api.views import service as service_views
from rest_framework_extensions.routers import ExtendedSimpleRouter
from django.urls import re_path

app_name = 'registry'

nested_api_router = ExtendedSimpleRouter()
(
    nested_api_router.register(r'services', service_views.ServiceViewSet, basename='service')
                     .register(r'layers', service_views.LayerViewSet, basename='service-layers', parents_query_lookups=['service'])
                     # .register(r'featuretypes', service_views.FeatureTypeViewSet, basename='services-feature_type', parents_query_lookups=['service']) 

)

urlpatterns = nested_api_router.urls
urlpatterns.extend([
    re_path(r'^services/(?P<pk>[^/.]+)/relationships/(?P<related_field>[-/w]+)$', service_views.ServiceRelationshipView, name='service-relationships')
])
