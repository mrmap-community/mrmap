from django.urls import path
from resourceNew.autocompletes import security as security_views

app_name = "resourceNew.autocomplete"
urlpatterns = [
    path('wms-operations/', security_views.WmsOperationsAutocomplete.as_view(), name="ogcoperation_wms_ac"),
    path('wfs-operations/', security_views.WfsOperationsAutocomplete.as_view(), name="ogcoperation_wfs_ac"),
]

