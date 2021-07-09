from django.urls import path
from resourceNew.views import service as service_views
from resourceNew.views import metadata as metadata_views
from resourceNew.views import ows as ows_views
from resourceNew.views import security as security_views
from resourceNew.wizards import security as security_wizards
from resourceNew.wizards.security import ALLOWED_OPERATION_WIZARD_FORMS

app_name = 'resourceNew'
urlpatterns = [
    # Service views
    path("service/add", service_views.RegisterServiceFormView.as_view(), name="service_add"),
    path("service/wms", service_views.WmsListView.as_view(), name="service_wms_list"),
    path("service/layers", service_views.LayerListView.as_view(), name="layer_list"),
    path("service/wfs", service_views.WfsListView.as_view(), name="service_wfs_list"),
    path("service/featuretypes", service_views.FeatureTypeListView.as_view(), name="feature_type_list"),
    path("service/featuretypeelements", service_views.FeatureTypeElementListView.as_view(), name="feature_type_element_list"),

    path("service/<pk>/operation", ows_views.GenericOwsServiceOperationFacade.as_view(), name="service_operation_view"),
    path("service/<pk>/xml", service_views.ServiceXmlView.as_view(), name="service_xml_view"),
    path("service/<pk>/activate", service_views.ServiceActivateView.as_view(), name="service_activate"),
    path("service/<pk>/change", service_views.ServiceUpdateView.as_view(), name="service_change"),
    path("service/<pk>/delete", service_views.ServiceDeleteView.as_view(), name="service_delete"),

    path("service/wms/<pk>/tree", service_views.ServiceWmsTreeView.as_view(), name="service_wms_tree_view"),
    path("service/wfs/<pk>/tree", service_views.ServiceWfsTreeView.as_view(), name="service_wfs_tree_view"),

    path("service/layers/<pk>/change", service_views.LayerUpdateView.as_view(), name="layer_change"),
    path("service/featuretypes/<pk>/change", service_views.FeatureTypeUpdateView.as_view(), name="feature_type_change"),

    # Metadata views
    path("metadata/services", metadata_views.ServiceMetadataListView.as_view(), name="service_metadata_list"),
    path("metadata/layers", metadata_views.LayerMetadataListView.as_view(), name="layer_metadata_list"),
    path("metadata/featuretypes", metadata_views.FeatureTypeMetadataListView.as_view(), name="feature_type_metadata_list"),
    path("metadata/datasets", metadata_views.DatasetMetadataListView.as_view(), name="dataset_metadata_list"),

    path("metadata/services/<pk>/xml", metadata_views.ServiceMetadataXmlView.as_view(), name="service_metadata_xml_view"),
    path("metadata/services/<pk>/change", metadata_views.ServiceMetadataUpdateView.as_view(), name="service_metadata_change"),

    path("metadata/datasets/<pk>/xml", metadata_views.DatasetMetadataXmlView.as_view(), name="dataset_metadata_xml_view"),
    path("metadata/datasets/<pk>/change", metadata_views.DatasetMetadataUpdateView.as_view(), name="dataset_metadata_change"),
    path("metadata/datasets/<pk>/restore", metadata_views.DatasetMetadataRestoreView.as_view(), name="dataset_metadata_restore"),

    # Security views
    path("security/external-authentications", security_views.ExternalAuthenticationListView.as_view(), name="external_authentication_list"),
    path("security/external-authentications/add", security_views.ExternalAuthenticationAddView.as_view(), name="external_authentication_add"),
    path("security/external-authentications/<pk>/change", security_views.ExternalAuthenticationChangeView.as_view(), name="external_authentication_change"),
    path("security/external-authentications/<pk>/delete", security_views.ExternalAuthenticationDeleteView.as_view(), name="external_authentication_delete"),

    path("security/service-access-groups", security_views.ServiceAccessGroupListView.as_view(), name="service_access_group_list"),
    path("security/service-access-groups/add", security_views.ServiceAccessGroupCreateView.as_view(), name="service_access_group_add"),
    path("security/service-access-groups/<pk>/change", security_views.ServiceAccessGroupChangeView.as_view(), name="service_access_group_change"),
    path("security/service-access-groups/<pk>/delete", security_views.ServiceAccessGroupDeleteView.as_view(), name="service_access_group_delete"),

    path("security/allowed-operations", security_views.AllowedOperationListView.as_view(), name="allowed_operation_list"),
    path("security/allowed-operations/add", security_wizards.AllowedOperationWizard.as_view(form_list=ALLOWED_OPERATION_WIZARD_FORMS), name="allowed_operation_add"),
    path("security/allowed-operations/<pk>/change", security_views.AllowedOperationChangeView.as_view(), name="allowed_operation_change"),
    path("security/allowed-operations/<pk>/delete", security_views.AllowedOperationDeleteView.as_view(), name="allowed_operation_delete"),

    path("security/proxy-settings", security_views.ProxySettingListView.as_view(), name="proxy_setting_list"),
    path("security/proxy-settings/add", security_views.ProxySettingCreateView.as_view(), name="proxy_setting_add"),
    path("security/proxy-settings/<pk>/change", security_views.ProxySettingUpdateView.as_view(), name="proxy_setting_change"),

    path("security/proxy-logs", security_views.AnalyzedResponseLogListView.as_view(), name="proxy_log_list")
]

