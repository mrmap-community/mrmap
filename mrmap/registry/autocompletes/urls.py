from django.urls import path
from registry.autocompletes import security as security_views
from registry.autocompletes import service as service_views
from registry.autocompletes import metadata as metadata_views
from registry.autocompletes import monitoring as monitoring_views

app_name = "registry.autocomplete"
urlpatterns = [
    # security models
    path('wms-operations', security_views.WmsOperationsAutocomplete.as_view(), name="ogcoperation_wms_ac"),
    path('wfs-operations', security_views.WfsOperationsAutocomplete.as_view(), name="ogcoperation_wfs_ac"),
    path('secure-able-operations', security_views.SecureAbleOperationsAutocomplete.as_view(), name="ogcoperation_secure_able_ac"),

    path('allowed-operations', security_views.AllowedOperationsAutocomplete.as_view(), name="allowedoperation_ac"),
    path('service-access-groups', security_views.ServiceAccessGroupAutocomplete.as_view(), name="service_access_group_ac"),

    # service
    path('services', service_views.ServiceAutocomplete.as_view(), name="service_ac"),
    path('feature-type', service_views.FeatureTypeAutocomplete.as_view(), name="feature_type_ac"),

    # metadata
    path('keywords', metadata_views.KeywordAutocomplete.as_view(), name="keyword_ac"),
    path('md-c', metadata_views.MetadataContactAutocomplete.as_view(), name="metadata_contact_ac"),
    path('crs', metadata_views.ReferenceSystemAutocomplete.as_view(), name="reference_system_ac"),
    path('dataset-metadata/', metadata_views.DatasetMetadataAutocomplete.as_view(), name='dataset_metadata_ac'),

    # monitoring
    path('monitoring-run', monitoring_views.MonitoringRunAutocomplete.as_view(), name="monitoring_run_ac"),
    path('monitoring-result', monitoring_views.MonitoringResultAutocomplete.as_view(), name="monitoring_result_ac"),
    path('monitoring-health-state', monitoring_views.HealthStateAutocomplete.as_view(), name="monitoring_health_state_ac"),
]
