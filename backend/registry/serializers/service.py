from accounts.models.groups import Organization
from accounts.serializers.users import UserSerializer
from django.utils.translation import gettext_lazy as _
from extras.serializers import (HistoryInformationSerializer,
                                ObjectPermissionCheckerSerializer,
                                StringRepresentationSerializer)
from MrMap.validators import validate_get_capablities_uri
from registry.models.metadata import (DatasetMetadata, Keyword,
                                      MetadataContact, ReferenceSystem, Style)
from registry.models.security import (AllowedWebMapServiceOperation,
                                      WebFeatureServiceAuthentication,
                                      WebMapServiceAuthentication)
from registry.models.service import (CatalougeService,
                                     CatalougeServiceOperationUrl, FeatureType,
                                     Layer, WebFeatureService,
                                     WebFeatureServiceOperationUrl,
                                     WebMapService, WebMapServiceOperationUrl)
from registry.serializers.metadata import (DatasetMetadataSerializer,
                                           KeywordSerializer,
                                           MetadataContactSerializer,
                                           StyleSerializer)
from registry.serializers.security import WebFeatureServiceOperationSerializer
from rest_framework.fields import BooleanField, IntegerField, URLField
from rest_framework_gis.fields import GeometryField
from rest_framework_json_api.relations import (
    ResourceRelatedField, SerializerMethodResourceRelatedField)
from rest_framework_json_api.serializers import (HyperlinkedIdentityField,
                                                 ModelSerializer,
                                                 SerializerMethodField)


class WebMapServiceOperationUrlSerializer(ModelSerializer):

    url = SerializerMethodField()

    class Meta:
        model = WebMapServiceOperationUrl
        fields = "__all__"

    def get_url(self, instance):
        return instance.get_url(request=self.context["request"])


class LayerSerializer(
        StringRepresentationSerializer,
        ModelSerializer):
    url = HyperlinkedIdentityField(
        view_name="registry:layer-detail",
        read_only=True,
    )

    service = ResourceRelatedField(
        label=_("web map service"),
        help_text=_("the web map service, where this layer is part of."),
        read_only=True,
        model=WebMapService,
    )
    keywords = ResourceRelatedField(
        label=_("keywords"),
        help_text=_("keywords help to find layers by matching keywords."),
        queryset=Keyword.objects,
        many=True,  # necessary for M2M fields & reverse FK fields
        related_link_view_name="registry:layer-keywords-list",
        related_link_url_kwarg="parent_lookup_layer",
    )

    # FIXME: prefetch ancestors for the following fields, cause otherwise this results in extra db transactions...
    bbox_lat_lon = GeometryField(
        source="get_bbox",
        label=_("bbox"),
        help_text=_("this is the spatial extent of the layer."))
    scale_min = IntegerField(
        source="get_scale_min",
        label=_("minimal scale"),
        help_text=_("the minimum scale value."))
    scale_max = IntegerField(
        source="get_scale_max",
        label=_("maximum scale"),
        help_text=_("the maximum scale value."))
    styles = ResourceRelatedField(
        label=_("styles"),
        help_text=_("related styles of this layer."),
        queryset=Style.objects,
        many=True,  # necessary for M2M fields & reverse FK fields
        related_link_view_name="registry:layer-styles-list",
        related_link_url_kwarg="parent_lookup_layer",
    )
    reference_systems = SerializerMethodResourceRelatedField(
        label=_("reference systems"),
        help_text=_("available reference systems of this layer."),
        model=ReferenceSystem,
        many=True,
        read_only=True,
    )

    included_serializers = {
        "service": "registry.serializers.service.WebMapServiceSerializer",
        "service.operation_urls": WebMapServiceOperationUrlSerializer,
        "styles": StyleSerializer,
        "keywords": KeywordSerializer,
        # TODO: "reference_systems": ReferenceSystemSerializer
    }

    class Meta:
        model = Layer
        fields = "__all__"

    def get_reference_systems(self, instance):
        return instance.get_reference_systems


class WebMapServiceSerializer(
    StringRepresentationSerializer,
    ObjectPermissionCheckerSerializer,
    HistoryInformationSerializer,
    ModelSerializer
):

    url = HyperlinkedIdentityField(
        view_name="registry:wms-detail",
    )

    layers = ResourceRelatedField(
        model=Layer,
        many=True,  # necessary for M2M fields & reverse FK fields
        related_link_view_name="registry:wms-layers-list",
        related_link_url_kwarg="parent_lookup_service",
        read_only=True,
    )

    service_contact = ResourceRelatedField(
        queryset=MetadataContact.objects,
        related_link_view_name="registry:wms-service-contact-list",
        related_link_url_kwarg="parent_lookup_service_contact_webmapservice_metadata",
    )
    metadata_contact = ResourceRelatedField(
        queryset=MetadataContact.objects,
        related_link_view_name="registry:wms-metadata-contact-list",
        related_link_url_kwarg="parent_lookup_metadata_contact_webmapservice_metadata",
    )
    keywords = ResourceRelatedField(
        queryset=Keyword.objects,
        many=True,
        related_link_view_name="registry:wms-keywords-list",
        related_link_url_kwarg="parent_lookup_ogcservice_metadata",
    )

    allowed_operations = ResourceRelatedField(
        queryset=AllowedWebMapServiceOperation.objects,
        many=True,
        related_link_view_name="registry:wms-allowedwmsoperation-list",
        related_link_url_kwarg="parent_lookup_secured_service",
        # meta_attrs={'keyword_count': 'count'}
    )

    operation_urls = ResourceRelatedField(
        label=_("operation urls"),
        help_text=_("this are the urls to use for the ogc operations."),
        model=WebMapServiceOperationUrl,
        many=True,
        read_only=True,
    )

    included_serializers = {
        "layers": LayerSerializer,
        "service_contact": MetadataContactSerializer,
        "metadata_contact": MetadataContactSerializer,
        "keywords": KeywordSerializer,
        "created_by": UserSerializer,
        "last_modified_by": UserSerializer,
        "operation_urls": WebMapServiceOperationUrlSerializer,
    }

    class Meta:
        model = WebMapService
        fields = "__all__"


class WebMapServiceCreateSerializer(ModelSerializer):

    get_capabilities_url = URLField(
        label=_("get capabilities url"),
        help_text=_("a valid get capabilities url."),
        # example="http://example.com/SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities",
        validators=[validate_get_capablities_uri])
    service_auth = ResourceRelatedField(
        queryset=WebMapServiceAuthentication.objects,
        required=False,
        label=_("authentication credentials"),
        help_text=_("Optional authentication credentials to request the remote service."))
    owner = ResourceRelatedField(
        queryset=Organization.objects,
        label=_("owner"),
        help_text=_("The selected organization grants all rights on the registered service."))
    collect_metadata_records = BooleanField(
        default=True,
        label=_("collect metadata records"),
        help_text=_("If checked, Mr. Map collects all related metadata documents after the registration task."))

    class Meta:
        model = WebMapService
        fields = (
            "get_capabilities_url",
            "owner",
            "service_auth",
            "collect_metadata_records",
        )


class WebFeatureServiceOperationUrlSerializer(ModelSerializer):

    url = SerializerMethodField()

    class Meta:
        model = WebFeatureServiceOperationUrl
        fields = "__all__"

    def get_url(self, instance):
        return instance.get_url(request=self.context["request"])


class FeatureTypeSerializer(
        StringRepresentationSerializer,
        ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name="registry:featuretype-detail",
        read_only=True,
    )

    service = ResourceRelatedField(
        label=_("web feature service"),
        help_text=_(
            "the web feature service, where this featuretype is part of."),
        read_only=True,
        model=WebFeatureService,
    )

    keywords = ResourceRelatedField(
        label=_("keywords"),
        help_text=_("keywords help to find featuretypes by matching keywords."),
        queryset=Keyword.objects,
        many=True,  # necessary for M2M fields & reverse FK fields
        related_link_view_name="registry:featuretype-keywords-list",
        related_link_url_kwarg="parent_lookup_featuretype",
    )

    reference_systems = ResourceRelatedField(
        label=_("reference systems"),
        help_text=_("available reference systems of this featuretype."),
        model=ReferenceSystem,
        many=True,
        read_only=True,
        related_link_view_name="registry:featuretype-referencesystems-list",
        related_link_url_kwarg="parent_lookup_featuretype",
    )

    included_serializers = {
        "service": "registry.serializers.service.WebFeatureServiceSerializer",
        "service.operation_urls": WebFeatureServiceOperationSerializer,
        "keywords": KeywordSerializer,
        # TODO: "reference_systems": ReferenceSystemSerializer
    }

    class Meta:
        model = FeatureType
        fields = "__all__"


class WebFeatureServiceSerializer(
        StringRepresentationSerializer,
        HistoryInformationSerializer,
        ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name="registry:wfs-detail",
    )

    featuretypes = ResourceRelatedField(
        queryset=FeatureType.objects,
        many=True,
        related_link_view_name="registry:wfs-featuretypes-list",
        related_link_url_kwarg="parent_lookup_service",
    )

    service_contact = ResourceRelatedField(
        queryset=MetadataContact.objects,
        related_link_view_name="registry:wfs-service-contact-list",
        related_link_url_kwarg="parent_lookup_service_contact_webfeatureservice_metadata",
    )
    metadata_contact = ResourceRelatedField(
        queryset=MetadataContact.objects,
        related_link_view_name="registry:wfs-metadata-contact-list",
        related_link_url_kwarg="parent_lookup_metadata_contact_webfeatureservice_metadata",
    )
    keywords = ResourceRelatedField(
        queryset=Keyword.objects,
        many=True,
        related_link_view_name="registry:wfs-keywords-list",
        related_link_url_kwarg="parent_lookup_ogcservice_metadata",
    )

    operation_urls = ResourceRelatedField(
        label=_("operation urls"),
        help_text=_("this are the urls to use for the ogc operations."),
        model=WebFeatureServiceOperationUrl,
        many=True,
        read_only=True,
    )

    included_serializers = {
        "featuretypes": FeatureTypeSerializer,
        "service_contact": MetadataContactSerializer,
        "metadata_contact": MetadataContactSerializer,
        "keywords": KeywordSerializer,
        "created_by": UserSerializer,
        "last_modified_by": UserSerializer,
        "operation_urls": WebFeatureServiceOperationUrlSerializer,
    }

    class Meta:
        model = WebFeatureService
        fields = "__all__"


class WebFeatureServiceCreateSerializer(ModelSerializer):
    get_capabilities_url = URLField(validators=[validate_get_capablities_uri])
    service_auth = ResourceRelatedField(
        queryset=WebFeatureServiceAuthentication.objects, required=False
    )
    owner = ResourceRelatedField(queryset=Organization.objects)

    collect_metadata_records = BooleanField(default=True)

    class Meta:
        model = WebFeatureService
        fields = (
            "get_capabilities_url",
            "owner",
            "service_auth",
            "collect_metadata_records",
        )


class CatalougeServiceCreateSerializer(ModelSerializer):
    get_capabilities_url = URLField(validators=[validate_get_capablities_uri])
    service_auth = ResourceRelatedField(
        queryset=WebFeatureServiceAuthentication.objects, required=False
    )
    owner = ResourceRelatedField(queryset=Organization.objects)

    class Meta:
        model = CatalougeService
        fields = (
            "get_capabilities_url",
            "owner",
            "service_auth",
        )


class CatalougeServiceSerializer(
        StringRepresentationSerializer,
        HistoryInformationSerializer,
        ModelSerializer):
    url = HyperlinkedIdentityField(
        view_name="registry:wfs-detail",
    )
    dataset_metadata = ResourceRelatedField(
        queryset=DatasetMetadata.objects,
        many=True,
        related_link_view_name="registry:csw-datasetmetadata-list",
        related_link_url_kwarg="parent_lookup_self_pointing_catalouge_service",
    )
    service_contact = ResourceRelatedField(
        queryset=MetadataContact.objects,
        related_link_view_name="registry:csw-service-contact-list",
        related_link_url_kwarg="parent_lookup_service_contact_catalougeservice_metadata",
    )
    metadata_contact = ResourceRelatedField(
        queryset=MetadataContact.objects,
        related_link_view_name="registry:csw-metadata-contact-list",
        related_link_url_kwarg="parent_lookup_metadata_contact_catalougeservice_metadata",
    )
    keywords = ResourceRelatedField(
        queryset=Keyword.objects,
        many=True,
        related_link_view_name="registry:csw-keywords-list",
        related_link_url_kwarg="parent_lookup_ogcservice_metadata",
    )
    operation_urls = ResourceRelatedField(
        label=_("operation urls"),
        help_text=_("this are the urls to use for the ogc operations."),
        model=CatalougeServiceOperationUrl,
        many=True,
        read_only=True,
    )

    included_serializers = {
        "dataset_metadata": DatasetMetadataSerializer,
        "service_contact": MetadataContactSerializer,
        "metadata_contact": MetadataContactSerializer,
        "keywords": KeywordSerializer,
        "created_by": UserSerializer,
        "last_modified_by": UserSerializer,
        "operation_urls": WebFeatureServiceOperationUrlSerializer,
    }

    class Meta:
        model = CatalougeService
        fields = "__all__"
