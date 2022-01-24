from django.urls import path
from rest_framework_extensions.routers import ExtendedSimpleRouter

from registry.views import mapcontext as mapcontext_views
from registry.views import metadata as metadata_views
from registry.views import security as security_views
from registry.views import service as service_views

app_name = 'registry'

router = ExtendedSimpleRouter()
(
    # web map service
    router.register(
        r'wms', service_views.WebMapServiceViewSet, basename='wms')
    .register(r'layers', service_views.LayerViewSet, basename='wms-layers', parents_query_lookups=['service']),
    router.register(
        r'wms', service_views.WebMapServiceViewSet, basename='wms')
    .register(r'service-contact', metadata_views.MetadataContactViewSet, basename='wms-service-contact', parents_query_lookups=['service_contact_webmapservice_metadata']),
    router.register(
        r'wms', service_views.WebMapServiceViewSet, basename='wms')
    .register(r'service-contact', metadata_views.MetadataContactViewSet, basename='wms-metadata-contact', parents_query_lookups=['metadata_contact_webmapservice_metadata']),
    router.register(
        r'wms', service_views.WebMapServiceViewSet, basename='wms')
    .register(r'keywords', metadata_views.KeywordViewSet, basename='wms-keywords', parents_query_lookups=['ogcservice_metadata']),
    router.register(
        r'wms', service_views.WebMapServiceViewSet, basename='wms')
    .register(r'allowed-wms-operations', security_views.AllowedWebMapServiceOperationViewSet, basename='wms-allowedwmsoperation', parents_query_lookups=['secured_service']),

    # layers
    router.register(r'layers', service_views.LayerViewSet, basename='layer')
    .register(r'styles', metadata_views.StyleViewSet, basename='layer-styles', parents_query_lookups=['layer']),
    router.register(r'layers', service_views.LayerViewSet, basename='layer')
    .register(r'keywords', metadata_views.KeywordViewSet, basename='layer-keywords', parents_query_lookups=['layer']),

    # web feature service
    router.register(
        r'wfs', service_views.WebFeatureServiceViewSet, basename='wfs')
    .register(r'featuretypes', service_views.FeatureTypeViewSet, basename='wfs-featuretypes', parents_query_lookups=['service']),

    # feature types
    router.register(r'featuretypes',
                    service_views.FeatureTypeViewSet, basename='featuretype')
    .register(r'keywords', metadata_views.KeywordViewSet, basename='featuretype-keywords', parents_query_lookups=['featuretype']),

    # map context
    router.register(
        r'mapcontexts', mapcontext_views.MapContextViewSet, basename='mapcontext')
    .register(r'mapcontextlayers', mapcontext_views.MapContextLayerViewSet, basename='mapcontext-mapcontextlayers', parents_query_lookups=['map_context']),
    router.register(r'mapcontextlayers',
                    mapcontext_views.MapContextLayerViewSet, basename='mapcontextlayer'),

    # metadata
    router.register(r'keywords', metadata_views.KeywordViewSet,
                    basename='keyword'),
    router.register(r'styles', metadata_views.StyleViewSet,
                    basename='style'),
    router.register(r'dataset-metadata',
                    metadata_views.DatasetMetadataViewSet, basename='datasetmetadata'),
    router.register(r'metadata-contacts',
                    metadata_views.MetadataContactViewSet, basename='metadatacontact'),

    # security
    router.register(r'security/wms-operations',
                    security_views.WebMapServiceOperationViewSet, basename='wmsoperation'),
    router.register(r'security/wfs-operations',
                    security_views.WebFeatureServiceOperationViewSet, basename='wfsoperation'),

    router.register(r'security/allowed-wms-operations',
                    security_views.AllowedWebMapServiceOperationViewSet, basename='allowedwmsoperation'),
    router.register(r'security/allowed-wfs-operations',
                    security_views.AllowedWebFeatureServiceOperationViewSet, basename='allowedwfsoperation'),
)

urlpatterns = router.urls

urlpatterns.extend([
    # path('wms/<created_by_pk>/created_by', service_views.WebMapServiceViewSet.as_view(actions={'get': 'retrieve'}), name='layer-wms-detail'),
    path('layers/<layer_pk>/service', service_views.WebMapServiceViewSet.as_view(
        actions={'get': 'retrieve'}), name='layer-wms-detail'),
])

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
