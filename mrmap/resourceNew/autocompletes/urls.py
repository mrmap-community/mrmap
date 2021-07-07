from django.urls import path
from resourceNew.autocompletes import security as security_views

app_name = "resourceNew.autocomplete"
urlpatterns = [

    # security models
    path('wms-operations/', security_views.WmsOperationsAutocomplete.as_view(), name="ogcoperation_wms_ac"),
    path('wfs-operations/', security_views.WfsOperationsAutocomplete.as_view(), name="ogcoperation_wfs_ac"),
    path('allowed-operations/', security_views.AllowedOperationsAutocomplete.as_view(), name="allowedoperation_ac"),

]

