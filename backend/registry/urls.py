from django.urls import path
from registry.views import harvesting as harvesting_views
from registry.views import mapcontext as mapcontext_views
from registry.views import metadata as metadata_views
from registry.views import monitoring as monitoring_views
from registry.views import security as security_views
from registry.views import service as service_views
from registry.views import stats as stats_views
from rest_framework_extensions.routers import ExtendedSimpleRouter

app_name = 'registry'

router = ExtendedSimpleRouter(trailing_slash=False)
(
    # web map service
    router.register(r'wms', service_views.WebMapServiceViewSet, basename='wms')
          .register(r'layers', service_views.NestedLayerViewSet, basename='wms-layers', parents_query_lookups=['service']),
    router.register(r'wms', service_views.WebMapServiceViewSet, basename='wms')
          .register(r'service-contact', metadata_views.NestedServiceContactViewSet, basename='wms-service-contact', parents_query_lookups=['service_contact_webmapservice_metadata']),
    router.register(r'wms', service_views.WebMapServiceViewSet, basename='wms')
          .register(r'metadata-contact', metadata_views.NestedMetadataContactViewSet, basename='wms-metadata-contact', parents_query_lookups=['metadata_contact_webmapservice_metadata']),
    router.register(r'wms', service_views.WebMapServiceViewSet, basename='wms')
          .register(r'keywords', metadata_views.NestedKeywordViewSet, basename='wms-keywords', parents_query_lookups=['webmapservice_metadata']),
    router.register(r'wms', service_views.WebMapServiceViewSet, basename='wms')
          .register(r'proxy-settings', security_views.NestedWebMapServiceProxySettingViewSet, basename='wms-proxy-settings', parents_query_lookups=['secured_service']),
    router.register(r'wms', service_views.WebMapServiceViewSet, basename='wms')
          .register(r'allowed-wms-operations', security_views.NestedAllowedWebMapServiceOperationViewSet, basename='wms-allowedwmsoperation', parents_query_lookups=['secured_service']),

    # historical
    router.register(r'wms-historical',
                    service_views.WebMapServiceHistoricalViewSet, basename='wms-historical'),

    # layer
    router.register(r'layers', service_views.LayerViewSet, basename='layer')
          .register(r'styles', metadata_views.NestedStyleViewSet, basename='layer-styles', parents_query_lookups=['layer']),
    router.register(r'layers', service_views.LayerViewSet,
                    basename='featuretype')
          .register(r'referencesystems', metadata_views.NestedReferenceSystemViewSet, basename='layer-referencesystems', parents_query_lookups=['layer']),
    router.register(r'layers', service_views.LayerViewSet, basename='layer')
          .register(r'keywords', metadata_views.NestedKeywordViewSet, basename='layer-keywords', parents_query_lookups=['layer_metadata']),
    router.register(r'layers', service_views.LayerViewSet, basename='layer')
          .register(r'dataset-metadata', metadata_views.NestedDatasetMetadataViewSet, basename='layer-datasetmetadata', parents_query_lookups=['self_pointing_layers']),

    # web feature service
    router.register(
        r'wfs', service_views.WebFeatureServiceViewSet, basename='wfs')
    .register(r'featuretypes', service_views.NestedFeatureTypeViewSet, basename='wfs-featuretypes', parents_query_lookups=['service']),
    router.register(
        r'wfs', service_views.WebFeatureServiceViewSet, basename='wfs')
    .register(r'service-contact', metadata_views.NestedServiceContactViewSet, basename='wfs-service-contact', parents_query_lookups=['service_contact_webfeatureservice_metadata']),
    router.register(
        r'wfs', service_views.WebFeatureServiceViewSet, basename='wfs')
    .register(r'metadata-contact', metadata_views.NestedMetadataContactViewSet, basename='wfs-metadata-contact', parents_query_lookups=['metadata_contact_webfeatureservice_metadata']),
    router.register(
        r'wfs', service_views.WebFeatureServiceViewSet, basename='wfs')
    .register(r'keywords', metadata_views.NestedKeywordViewSet, basename='wfs-keywords', parents_query_lookups=['webfeatureservice_metadata']),
    router.register(r'wfs', service_views.WebMapServiceViewSet, basename='wms')
          .register(r'proxy-settings', security_views.NestedWebFeatureServiceProxySettingViewSet, basename='wfs-proxy-settings', parents_query_lookups=['secured_service']),

    router.register(r'wfs', service_views.WebMapServiceViewSet, basename='wms')
          .register(r'allowed-wms-operations', security_views.NestedAllowedWebFeatureServiceOperationViewSet, basename='wfs-allowedwmsoperation', parents_query_lookups=['secured_service']),

    # feature types
    router.register(r'featuretypes',
                    service_views.FeatureTypeViewSet, basename='featuretype')
    .register(r'referencesystems', metadata_views.NestedReferenceSystemViewSet, basename='featuretype-referencesystems', parents_query_lookups=['featuretype']),
    router.register(r'featuretypes',
                    service_views.FeatureTypeViewSet, basename='featuretype')
    .register(r'keywords', metadata_views.NestedKeywordViewSet, basename='featuretype-keywords', parents_query_lookups=['featuretype_metadata']),
    router.register(
        r'wfs', service_views.WebFeatureServiceViewSet, basename='wfs')
    .register(r'allowed-wms-operations', security_views.NestedAllowedWebFeatureServiceOperationViewSet, basename='wfs-allowedwmsoperation', parents_query_lookups=['secured_service']),

    # catalogue service
    router.register(
        r'csw', service_views.CatalogueServiceViewSet, basename='csw')
    .register(r'dataset-metadata', metadata_views.NestedDatasetMetadataViewSet, basename='csw-datasetmetadata', parents_query_lookups=['harvested_through']),
    router.register(
        r'csw', service_views.CatalogueServiceViewSet, basename='csw')
    .register(r'keywords', metadata_views.NestedKeywordViewSet, basename='csw-keywords', parents_query_lookups=['catalogueservice_metadata']),
    router.register(
        r'csw', service_views.CatalogueServiceViewSet, basename='csw')
    .register(r'service-contact', metadata_views.NestedServiceContactViewSet, basename='csw-service-contact', parents_query_lookups=['service_contact_catalogueservice_metadata']),
    router.register(
        r'csw', service_views.CatalogueServiceViewSet, basename='csw')
    .register(r'metadata-contact', metadata_views.NestedMetadataContactViewSet, basename='csw-metadata-contact', parents_query_lookups=['metadata_contact_catalogueservice_metadata']),
    router.register(
        r'csw', service_views.CatalogueServiceViewSet, basename='csw')
    .register(r'harvesting-jobs', harvesting_views.NestedHarvestingJobViewSet, basename='csw-harvesting-jobs', parents_query_lookups=['service']),

    # harvesting
    router.register(r'harvesting/harvesting-jobs',
                    harvesting_views.HarvestingJobViewSet, basename='harvestingjob')
    .register(r'temporary-md-metadata-files', harvesting_views.NestedTemporaryMdMetadataFileViewSet, basename='harvestingjob-temporarymdmetadatafiles', parents_query_lookups=['job']),

    router.register(r'harvesting/harvesting-jobs',
                    harvesting_views.HarvestingJobViewSet, basename='harvestingjob')
    .register(r'harvested-metadata-records', harvesting_views.NestedHarvestedMetadataRelationViewSet, basename='harvestingjob-harvestedmetadatarelations', parents_query_lookups=['harvesting_job']),

    router.register(r'harvesting/harvesting-jobs',
                    harvesting_views.HarvestingJobViewSet, basename='harvestingjob')
    .register(r'harvested-dataset-metadata-records', metadata_views.NestedDatasetMetadataViewSet, basename='harvestingjob-harvesteddatasetmetadata', parents_query_lookups=['harvested_dataset_metadata_relation__harvesting_job']),

    router.register(r'harvesting/harvesting-jobs',
                    harvesting_views.HarvestingJobViewSet, basename='harvestingjob')
    .register(r'harvested-service-metadata-records', metadata_views.NestedServiceMetadataViewSet, basename='harvestingjob-harvestedservicemetadata', parents_query_lookups=['harvested_service_metadata_relation__harvesting_job']),

    router.register(r'harvesting/temporary-md-metadata-file',
                    harvesting_views.TemporaryMdMetadataFileViewSet, basename='temporarymdmetadatafile'),
    router.register(r'harvesting/harvested-metadata-records',
                    harvesting_views.HarvestedMetadataRelationViewSet, basename='harvestedmetadatarelation'),


    # map context
    router.register(
        r'mapcontexts', mapcontext_views.MapContextViewSet, basename='mapcontext')
    .register(r'mapcontextlayers', mapcontext_views.NestedMapContextLayerViewSet, basename='mapcontext-mapcontextlayers', parents_query_lookups=['map_context']),
    router.register(r'mapcontextlayers',
                    mapcontext_views.MapContextLayerViewSet, basename='mapcontextlayer'),

    # metadata
    router.register(r'keywords', metadata_views.KeywordViewSet,
                    basename='keyword'),
    router.register(r'licences', metadata_views.LicenceViewSet,
                    basename='licence'),
    router.register(r'referencesystems',
                    metadata_views.ReferenceSystemViewSet, basename='referencesystem'),
    router.register(r'styles', metadata_views.StyleViewSet, basename='style'),
    router.register(r'metadata-contacts',
                    metadata_views.MetadataContactViewSet, basename='metadatacontact'),

    # dataset metadata records
    router.register(r'dataset-metadata',
                    metadata_views.DatasetMetadataViewSet, basename='datasetmetadata')
    .register(r'keywords', metadata_views.NestedKeywordViewSet, basename='datasetmetadata-keywords', parents_query_lookups=['datasetmetadata_metadata']),
    router.register(r'dataset-metadata',
                    metadata_views.DatasetMetadataViewSet, basename='datasetmetadata')
    .register(r'licence', metadata_views.NestedLicenceViewSet, basename='datasetmetadata-licence', parents_query_lookups=['datasetmetadata']),
    router.register(r'dataset-metadata',
                    metadata_views.DatasetMetadataViewSet, basename='datasetmetadata')
    .register(r'dataset-contact', metadata_views.NestedDatasetContactViewSet, basename='datasetmetadata-datasetcontact', parents_query_lookups=['datasetmetadatarecord_dataset_contact']),
    router.register(r'dataset-metadata',
                    metadata_views.DatasetMetadataViewSet, basename='datasetmetadata')
    .register(r'metadata-contact', metadata_views.NestedMetadataContactViewSet, basename='datasetmetadata-metadatacontact', parents_query_lookups=['datasetmetadatarecord_metadata_contact']),
    router.register(r'dataset-metadata',
                    metadata_views.DatasetMetadataViewSet, basename='datasetmetadata')
    .register(r'referencesystems', metadata_views.NestedReferenceSystemViewSet, basename='datasetmetadata-referencesystems', parents_query_lookups=['dataset_metadata']),
    router.register(r'dataset-metadata',
                    metadata_views.DatasetMetadataViewSet, basename='datasetmetadata')
    .register(r'csws', service_views.NestedCatalogueServiceViewSet, basename='datasetmetadata-csws', parents_query_lookups=['dataset_metadata_relation__dataset_metadata']),
    router.register(r'dataset-metadata',
                    metadata_views.DatasetMetadataViewSet, basename='datasetmetadata')
    .register(r'layers', service_views.NestedLayerViewSet, basename='datasetmetadata-layers', parents_query_lookups=['dataset_metadata_relation__dataset_metadata']),
    router.register(r'dataset-metadata',
                    metadata_views.DatasetMetadataViewSet, basename='datasetmetadata')
    .register(r'featuretypes', service_views.NestedFeatureTypeViewSet, basename='datasetmetadata-featuretypes', parents_query_lookups=['dataset_metadata_relation__dataset_metadata']),

    # service metadata records
    router.register(r'service-metadata',
                    metadata_views.ServiceMetadataViewSet, basename='servicemetadata'),
    router.register(r'service-metadata',
                    metadata_views.ServiceMetadataViewSet, basename='servicemetadata')
    .register(r'csws', service_views.NestedCatalogueServiceViewSet, basename='servicemetadata-csws', parents_query_lookups=['service_metadata_relation__service_metadata']),

    # security
    router.register(r'security/wms-authentication',
                    security_views.WebMapServiceAuthenticationViewSet, basename='wmsauth'),
    router.register(r'security/wms-operations',
                    security_views.WebMapServiceOperationViewSet, basename='wmsoperation'),
    router.register(r'security/wfs-authentication',
                    security_views.WebFeatureServiceAuthenticationViewSet, basename='wfsauth'),
    router.register(r'security/wfs-operations',
                    security_views.WebFeatureServiceOperationViewSet, basename='wfsoperation'),

    router.register(r'security/allowed-wms-operations',
                    security_views.AllowedWebMapServiceOperationViewSet, basename='allowedwmsoperation'),
    router.register(r'security/allowed-wfs-operations',
                    security_views.AllowedWebFeatureServiceOperationViewSet, basename='allowedwfsoperation'),

    router.register(r'security/wms-proxy-settings',
                    security_views.WebMapServiceProxySettingViewSet, basename='webmapserviceproxysetting'),
    router.register(r'security/wfs-proxy-settings',
                    security_views.WebFeatureServiceProxySettingViewSet, basename='webfeatureserviceproxysetting'),

    # monitoring
    router.register(r'monitoring/wms-monitoring-settings',
                    monitoring_views.WebMapServiceMonitoringSettingViewSet, basename='webmapservicemonitoringsetting')
    .register(r'get-capabilities-probes',
              monitoring_views.NestedGetCapabilitiesProbeViewSet,
              basename='webmapservicemonitoringsetting-getcap-probes',
              parents_query_lookups=['setting']),
    router.register(r'monitoring/wms-monitoring-settings',
                    monitoring_views.WebMapServiceMonitoringSettingViewSet, basename='webmapservicemonitoringsetting')
    .register(r'get-map-probes',
              monitoring_views.NestedGetMapProbeViewSet,
              basename='webmapservicemonitoringsetting-getmap-probes',
              parents_query_lookups=['setting']),
    router.register(r'monitoring/wms-monitoring-get-capabilities-probes',
                    monitoring_views.GetCapabilitiesProbeViewSet, basename='webmapservicemonitoring-getcapabilities-probe'),
    router.register(r'monitoring/wms-monitoring-get-map-probes',
                    monitoring_views.GetMapProbeViewSet, basename='webmapservicemonitoring-getmap-probe'),
    router.register(r'monitoring/wms-monitoring-runs',
                    monitoring_views.WebMapServiceMonitoringRunViewSet, basename='webmapservicemonitoringrun')
    .register(r'get-cap-probe-results',
              monitoring_views.NestedGetCapabilitiesProbeResultViewSet,
              basename='webmapservicemonitoringsetting-getcap-probe-results',
              parents_query_lookups=['run']),
    router.register(r'monitoring/wms-monitoring-runs',
                    monitoring_views.WebMapServiceMonitoringRunViewSet, basename='webmapservicemonitoringrun')
    .register(r'get-map-probe-results',
              monitoring_views.NestedGetMapProbeResultViewSet,
              basename='webmapservicemonitoringsetting-getmap-probe-results',
              parents_query_lookups=['run']),
    router.register(r'monitoring/wms-monitoring-get-capabilitites-probe-results',
                    monitoring_views.GetCapabilitiesProbeResultViewSet, basename='webmapservicemonitoring-getcapabilities-probe-result'),
    router.register(r'monitoring/wms-monitoring-get-map-probe-results',
                    monitoring_views.GetMapProbeResultViewSet, basename='webmapservicemonitoring-getmap-probe-result'),
)

urlpatterns = router.urls + [
    path(
        route=r'statistical/dataset-metadata-records',
        view=stats_views.StatisticalDatasetMetadataRecordListView.as_view(),
        name='statistical-dataset-metadata-records'
    )
]
# + [
#    path(
#        # ^harvesting/harvesting-jobs/(?P<pk>[^/.]+)$
#        # route=r'^bla/(?P<pk>[^/.]+)/relationships/(?P<related_field>[-/w]+)$',
#        route='harvesting/harvesting-jobs/<pk>/relationships/<related_field>',
#        view=HarvestingJobRelationshipView.as_view(),#
#        name="harvesting-job-relationships"
#    ),
# ]
