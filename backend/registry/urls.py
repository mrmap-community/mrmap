from django.urls import path
from rest_framework_extensions.routers import ExtendedSimpleRouter

from registry.views import jobs as jobs_views
from registry.views import mapcontext as mapcontext_views
from registry.views import metadata as metadata_views
from registry.views import service as service_views

app_name = 'registry'

nested_api_router = ExtendedSimpleRouter()
(
    # ogc service
    nested_api_router.register(
        r'ogcservices', service_views.OgcServiceViewSet, basename='ogcservice'),

    # web map service
    nested_api_router.register(
        r'wms', service_views.WebMapServiceViewSet, basename='wms')
    .register(r'layers', service_views.LayerViewSet, basename='wms-layers', parents_query_lookups=['service']),
    nested_api_router.register(
        r'layers', service_views.LayerViewSet, basename='layer')
    .register(r'styles', metadata_views.StyleViewSet, basename='layer-styles', parents_query_lookups=['layer']),
    nested_api_router.register(
        r'layers', service_views.LayerViewSet, basename='layer')
    .register(r'keywords', metadata_views.KeywordViewSet, basename='layer-keywords', parents_query_lookups=['layer']),
    # web feature service
    nested_api_router.register(
        r'wfs', service_views.WebFeatureServiceViewSet, basename='wfs')
    .register(r'featuretypes', service_views.FeatureTypeViewSet, basename='wfs-featuretypes', parents_query_lookups=['service']),
    nested_api_router.register(
        r'featuretypes', service_views.FeatureTypeViewSet, basename='featuretype')
    .register(r'keywords', metadata_views.KeywordViewSet, basename='featuretype-keywords', parents_query_lookups=['featuretype']),

    # # map context
    nested_api_router.register(
        r'mapcontexts', mapcontext_views.MapContextViewSet, basename='mapcontext')
    .register(r'mapcontextlayers', mapcontext_views.MapContextLayerViewSet, basename='mapcontext-mapcontextlayers', parents_query_lookups=['map_context']),
    nested_api_router.register(
        r'mapcontextlayers', mapcontext_views.MapContextLayerViewSet, basename='mapcontextlayer'),

    # # metadata
    nested_api_router.register(
        r'keywords', metadata_views.KeywordViewSet, basename='keyword'),
    nested_api_router.register(
        r'styles', metadata_views.StyleViewSet, basename='style'),
    nested_api_router.register(
        r'dataset-metadata', metadata_views.DatasetMetadataViewSet, basename='datasetmetadata'),

    # jobs
    nested_api_router.register(
        r'task-results', jobs_views.TaskResultReadOnlyViewSet, basename='taskresult')
)

urlpatterns = nested_api_router.urls
urlpatterns.extend([
    path('wms/<pk>/relationships/<related_field>',
         service_views.WebMapServiceRelationshipView.as_view(), name='wms-relationships'),
    path('layers/<pk>/relationships/<related_field>',
         service_views.LayerRelationshipView.as_view(), name='layer-relationships'),
    path('wfs/<pk>/relationships/<related_field>',
         service_views.WebFeatureServiceRelationshipView.as_view(), name='wfs-relationships'),
    path('featuretypes/<pk>/relationships/<related_field>',
         service_views.FeatureTypeRelationshipView.as_view(), name='featuretype-relationships'),
    path('mapcontexts/<pk>relationships/<related_field>',
         mapcontext_views.MapContextRelationshipView.as_view(), name='mapcontext-relationships'),
    path('mapcontextlayers/<pk>relationships/<related_field>',
         mapcontext_views.MapContextLayerRelationshipView.as_view(), name='mapcontextlayer-relationships')
])
