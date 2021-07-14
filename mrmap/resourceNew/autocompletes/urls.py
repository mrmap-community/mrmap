from django.urls import path
from resourceNew.autocompletes import security as security_views
from resourceNew.autocompletes import service as service_views

app_name = "resourceNew.autocomplete"
urlpatterns = [

    # security models
    path('wms-operations/', security_views.WmsOperationsAutocomplete.as_view(), name="ogcoperation_wms_ac"),
    path('wfs-operations/', security_views.WfsOperationsAutocomplete.as_view(), name="ogcoperation_wfs_ac"),
    path('secure-able-operations', security_views.SecureAbleOperationsAutocomplete.as_view(), name="ogcoperation_secure_able_ac"),

    path('allowed-operations/', security_views.AllowedOperationsAutocomplete.as_view(), name="allowedoperation_ac"),

    path('services/', service_views.ServiceAutocomplete.as_view(), name="service_ac"),

]

