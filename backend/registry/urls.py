from rest_framework_extensions.routers import ExtendedSimpleRouter

from registry.views import harvesting as harvesting_views
from registry.views import mapcontext as mapcontext_views
from registry.views import metadata as metadata_views
from registry.views import monitoring as monitoring_views
from registry.views import security as security_views
from registry.views import service as service_views

app_name = 'registry'

router = ExtendedSimpleRouter()
(
    # web map service
    router.register(r'wms', service_views.WebMapServiceViewSet, basename='wms')
          .register(r'layers', service_views.NestedLayerViewSet, basename='wms-layers', parents_query_lookups=['service']),
    router.register(r'wms', service_views.WebMapServiceViewSet, basename='wms')
          .register(r'service-contact', metadata_views.NestedServiceContactViewSet, basename='wms-service-contact', parents_query_lookups=['service_contact_webmapservice_metadata']),
    router.register(r'wms', service_views.WebMapServiceViewSet, basename='wms')
          .register(r'metadata-contact', metadata_views.NestedMetadataContactViewSet, basename='wms-metadata-contact', parents_query_lookups=['metadata_contact_webmapservice_metadata']),
    router.register(r'wms', service_views.WebMapServiceViewSet, basename='wms')
          .register(r'keywords', metadata_views.NestedKeywordViewSet, basename='wms-keywords', parents_query_lookups=['ogcservice_metadata']),
    router.register(r'layers', service_views.LayerViewSet, basename='layer')
          .register(r'styles', metadata_views.NestedStyleViewSet, basename='layer-styles', parents_query_lookups=['layer']),
    router.register(r'layers', service_views.LayerViewSet, basename='featuretype')
          .register(r'referencesystems', metadata_views.NestedReferenceSystemViewSet, basename='layer-referencesystems', parents_query_lookups=['layer']),
    router.register(r'layers', service_views.LayerViewSet, basename='layer')
          .register(r'keywords', metadata_views.NestedKeywordViewSet, basename='layer-keywords', parents_query_lookups=['layer']),
    router.register(r'wms', service_views.WebMapServiceViewSet, basename='wms')
          .register(r'allowed-wms-operations', security_views.NestedAllowedWebMapServiceOperationViewSet, basename='wms-allowedwmsoperation', parents_query_lookups=['secured_service']),

    # web feature service
    router.register(r'wfs', service_views.WebFeatureServiceViewSet, basename='wfs')
          .register(r'featuretypes', service_views.NestedFeatureTypeViewSet, basename='wfs-featuretypes', parents_query_lookups=['service']),
    router.register(r'wfs', service_views.WebFeatureServiceViewSet, basename='wfs')
          .register(r'service-contact', metadata_views.NestedServiceContactViewSet, basename='wfs-service-contact', parents_query_lookups=['service_contact_webfeatureservice_metadata']),
    router.register(r'wfs', service_views.WebFeatureServiceViewSet, basename='wfs')
          .register(r'metadata-contact', metadata_views.NestedMetadataContactViewSet, basename='wfs-metadata-contact', parents_query_lookups=['metadata_contact_webfeatureservice_metadata']),
    router.register(r'wfs', service_views.WebFeatureServiceViewSet, basename='wfs')
          .register(r'keywords', metadata_views.NestedKeywordViewSet, basename='wfs-keywords', parents_query_lookups=['ogcservice_metadata']),
    router.register(r'featuretypes', service_views.FeatureTypeViewSet, basename='featuretype')
          .register(r'referencesystems', metadata_views.NestedReferenceSystemViewSet, basename='featuretype-referencesystems', parents_query_lookups=['featuretype']),
    router.register(r'featuretypes', service_views.FeatureTypeViewSet, basename='featuretype')
          .register(r'keywords', metadata_views.NestedKeywordViewSet, basename='featuretype-keywords', parents_query_lookups=['featuretype']),
    router.register(r'wfs', service_views.WebFeatureServiceViewSet, basename='wfs')
          .register(r'allowed-wms-operations', security_views.NestedAllowedWebFeatureServiceOperationViewSet, basename='wfs-allowedwmsoperation', parents_query_lookups=['secured_service']),

    # catalouge service
    router.register(r'csw', service_views.CatalougeServiceViewSet, basename='csw')
          .register(r'dataset-metadata', metadata_views.NestedDatasetMetadataViewSet, basename='csw-datasetmetadata', parents_query_lookups=['self_pointing_catalouge_service']),
    router.register(r'csw', service_views.CatalougeServiceViewSet, basename='csw')
          .register(r'keywords', metadata_views.NestedKeywordViewSet, basename='csw-keywords', parents_query_lookups=['ogcservice_metadata']),
    router.register(r'csw', service_views.CatalougeServiceViewSet, basename='csw')
          .register(r'service-contact', metadata_views.NestedServiceContactViewSet, basename='csw-service-contact', parents_query_lookups=['service_contact_catalougeservice_metadata']),
    router.register(r'csw', service_views.CatalougeServiceViewSet, basename='csw')
          .register(r'metadata-contact', metadata_views.NestedMetadataContactViewSet, basename='csw-metadata-contact', parents_query_lookups=['metadata_contact_catalougeservice_metadata']),

    # harvesting
    router.register(r'harvesting/harvesting-jobs', harvesting_views.HarvestingJobViewSet, basename='harvestingjob'),

    # map context
    router.register(r'mapcontexts', mapcontext_views.MapContextViewSet, basename='mapcontext')
          .register(r'mapcontextlayers', mapcontext_views.NestedMapContextLayerViewSet, basename='mapcontext-mapcontextlayers', parents_query_lookups=['map_context']),
    router.register(r'mapcontextlayers', mapcontext_views.MapContextLayerViewSet, basename='mapcontextlayer'),

    # metadata
    router.register(r'keywords', metadata_views.KeywordViewSet, basename='keyword'),
    router.register(r'licences', metadata_views.LicenceViewSet, basename='licence'),
    router.register(r'referencesystems', metadata_views.ReferenceSystemViewSet, basename='referencesystem'),
    router.register(r'styles', metadata_views.StyleViewSet, basename='style'),
    router.register(r'metadata-contacts', metadata_views.MetadataContactViewSet, basename='metadatacontact'),

    # metadata records
    router.register(r'dataset-metadata', metadata_views.DatasetMetadataViewSet, basename='datasetmetadata')
          .register(r'keywords', metadata_views.NestedKeywordViewSet, basename='datasetmetadata-keywords', parents_query_lookups=['datasetmetadata_metadata']),
    router.register(r'dataset-metadata', metadata_views.DatasetMetadataViewSet, basename='datasetmetadata')
          .register(r'licence', metadata_views.NestedLicenceViewSet, basename='datasetmetadata-licence', parents_query_lookups=['datasetmetadata']),
    router.register(r'dataset-metadata', metadata_views.DatasetMetadataViewSet, basename='datasetmetadata')
          .register(r'dataset-contact', metadata_views.NestedMetadataContactViewSet, basename='datasetmetadata-datasetcontact', parents_query_lookups=['dataset_contact_metadata']),
    router.register(r'dataset-metadata', metadata_views.DatasetMetadataViewSet, basename='datasetmetadata')
          .register(r'metadata-contact', metadata_views.NestedMetadataContactViewSet, basename='datasetmetadata-metadatacontact', parents_query_lookups=['metadata_contact_metadata']),
    router.register(r'dataset-metadata', metadata_views.DatasetMetadataViewSet, basename='datasetmetadata')
          .register(r'referencesystems', metadata_views.NestedReferenceSystemViewSet, basename='datasetmetadata-referencesystems', parents_query_lookups=['dataset_metadata']),
    router.register(r'dataset-metadata', metadata_views.DatasetMetadataViewSet, basename='datasetmetadata')
          .register(r'csws', service_views.NestedCatalougeServiceViewSet, basename='datasetmetadata-csws', parents_query_lookups=['dataset_metadata_relation__dataset_metadata']),
    router.register(r'dataset-metadata', metadata_views.DatasetMetadataViewSet, basename='datasetmetadata')
          .register(r'layers', service_views.NestedLayerViewSet, basename='datasetmetadata-layers', parents_query_lookups=['dataset_metadata_relation__dataset_metadata']),
    router.register(r'dataset-metadata', metadata_views.DatasetMetadataViewSet, basename='datasetmetadata')
          .register(r'featuretypes', service_views.NestedFeatureTypeViewSet, basename='datasetmetadata-featuretypes', parents_query_lookups=['dataset_metadata_relation__dataset_metadata']),

    # security
    router.register(r'security/wms-authentication', security_views.WebMapServiceAuthenticationViewSet, basename='wmsauth'),
    router.register(r'security/wms-operations', security_views.WebMapServiceOperationViewSet, basename='wmsoperation'),
    router.register(r'security/wfs-operations', security_views.WebFeatureServiceOperationViewSet, basename='wfsoperation'),

    router.register(r'security/allowed-wms-operations', security_views.AllowedWebMapServiceOperationViewSet, basename='allowedwmsoperation'),
    router.register(r'security/allowed-wfs-operations', security_views.AllowedWebFeatureServiceOperationViewSet, basename='allowedwfsoperation'),

    # monitoring
    router.register(r'monitoring/wms-get-capabilities-result', monitoring_views.WMSGetCapabilitiesResultViewSet, basename='wmsgetcapabilitiesresult'),
    router.register(r'monitoring/layer-get-map-result', monitoring_views.LayerGetMapResultViewSet, basename='layergetmapresult'),
    router.register(r'monitoring/layer-get-feature-info-result', monitoring_views.LayerGetFeatureInfoResultViewSet, basename='layergetfeatureinforesult'),
)

urlpatterns = router.urls
