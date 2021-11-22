from django.urls import path

from registry.views import ows as ows_views
from registry.views import service as service_views
from registry.views import xml as xml_views

app_name = 'registry'

urlpatterns = [
    # Service views
    path("ogcservice/add", service_views.RegisterServiceFormView.as_view(), name="service_add"),

    # security proxy
    path("ogcservice/<pk>/operation", ows_views.GenericOwsServiceOperationFacade.as_view(), name="service_operation_view"),
    
    # Xml representation views
    path("wms/<pk>/xml", xml_views.WebMapServiceXmlView.as_view(), name="web_map_service_xml_view"),
    path("wms/layers/<pk>/xml", xml_views.LayerXmlView.as_view(), name="layer_xml_view"),

    path("wfs/<pk>/xml", xml_views.WebFeatureServiceXmlView.as_view(), name="web_feature_service_xml_view"),
    path("wfs/featuretypes/<pk>/xml", xml_views.FeatureTypeXmlView.as_view(), name="feature_type_xml_view"),

    path("metadata/wms/<pk>/xml", xml_views.WebMapServiceMetadataXmlView.as_view(), name="web_map_service_metadata_xml_view"),
    path("metadata/layers/<pk>/xml", xml_views.LayerMetadataXmlView.as_view(), name="layer_metadata_xml_view"),
    
    path("metadata/wfs/<pk>/xml", xml_views.WebFeatureServiceMetadataXmlView.as_view(), name="web_feature_service_metadata_xml_view"),
    path("metadata/featuretypes/<pk>/xml", xml_views.FeatureTypeMetadataXmlView.as_view(),
         name="feature_type_metadata_xml_view"),

    path("metadata/datasets/<pk>/xml", xml_views.DatasetMetadataXmlView.as_view(), name="dataset_metadata_xml_view"),

]
