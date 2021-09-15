from django.urls import path
from autocompletes import autocompletes


app_name = 'autocompletes'
urlpatterns = [
    path('kw/', autocompletes.KeywordAutocomplete.as_view(create_field="keyword"), name="keyword"),

    path("services", autocompletes.ServiceAutocomplete.as_view(), name="service"),
    path("service-access-groups", autocompletes.ServiceAccessGroupAutocomplete.as_view(), name="service_access_group"),
    path("layers", autocompletes.LayerAutocomplete.as_view(), name="layer"),
    path("feature-types", autocompletes.FeatureTypeAutocomplete.as_view(), name="feature_type"),

    path('md-contact/', autocompletes.MetadataContactAutocomplete.as_view(), name="metadata_contacts"),

    path('perm/', autocompletes.PermissionsAutocomplete.as_view(), name="permissions"),

    path('orga/', autocompletes.OrganizationAutocomplete.as_view(), name="organizations"),

    path('acl/', autocompletes.AccessControlListAutocomplete.as_view(), name="accesscontrollists"),

    path('rs/', autocompletes.ReferenceSystemAutocomplete.as_view(), name="reference_system"),
    path('ops/', autocompletes.OperationsAutocomplete.as_view(), name="operations"),
    path('users/', autocompletes.UsersAutocomplete.as_view(), name="users"),

    path('monitoring-run/', autocompletes.MonitoringRunAutocomplete.as_view(), name="monitoring_run"),
    path('monitoring-res/', autocompletes.MonitoringResultAutocomplete.as_view(), name="monitoring_result"),
    path('monitoring-hs/', autocompletes.HealthStateAutocomplete.as_view(), name="monitoring_healthstate"),

]
