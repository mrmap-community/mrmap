from django.urls import path
from autocompletes.autocompletes import *


app_name = 'autocompletes'
urlpatterns = [
    path('kw/', KeywordAutocomplete.as_view(create_field="keyword"), name="keyword"),
    path('cat/', CategoryAutocomplete.as_view(), name="category"),

    path('md/', MetadataAutocomplete.as_view(), name="metadata"),
    path('md-s/', MetadataServiceAutocomplete.as_view(), name="metadata_service"),
    path('md-d/', MetadataDatasetAutocomplete.as_view(), name="metadata_dataset"),
    path('md-l/', MetadataLayerAutocomplete.as_view(), name="metadata_layer"),
    path('md-ft/', MetadataFeaturetypeAutocomplete.as_view(), name="metadata_featuretype"),
    path('md-c/', MetadataCatalougeAutocomplete.as_view(), name="metadata_catalouge"),

    path('perm/', PermissionsAutocomplete.as_view(), name="permissions"),

    path('orga/', OrganizationAutocomplete.as_view(), name="organizations"),

    path('rs/', ReferenceSystemAutocomplete.as_view(), name="reference_system"),
    path('ops/', OperationsAutocomplete.as_view(), name="operations"),
    path('users/', UsersAutocomplete.as_view(), name="users"),

    path('monitoring-run/', MonitoringRunAutocomplete.as_view(), name="monitoring_run"),
    path('monitoring-res/', MonitoringResultAutocomplete.as_view(), name="monitoring_result"),
    path('monitoring-hs/', HealthStateAutocomplete.as_view(), name="monitoring.healthstate"),

]
