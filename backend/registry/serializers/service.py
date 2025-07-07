from typing import List

from accounts.models.groups import Organization
from accounts.serializers.users import UserSerializer
from django.utils.translation import gettext_lazy as _
from extras.serializers import (HistoryInformationSerializer,
                                ObjectPermissionCheckerSerializer,
                                StringRepresentationSerializer)
from extras.validators import validate_get_capablities_uri
from registry.models.harvest import HarvestingJob, PeriodicHarvestingJob
from registry.models.metadata import (DatasetMetadataRecord, Dimension,
                                      Keyword, MetadataContact,
                                      ReferenceSystem, Style)
from registry.models.security import (AllowedWebMapServiceOperation,
                                      WebFeatureServiceAuthentication,
                                      WebMapServiceAuthentication,
                                      WebMapServiceProxySetting)
from registry.models.service import (CatalogueService,
                                     CatalogueServiceOperationUrl, FeatureType,
                                     Layer, WebFeatureService,
                                     WebFeatureServiceOperationUrl,
                                     WebMapService, WebMapServiceOperationUrl)
from registry.serializers.metadata import (KeywordSerializer,
                                           MetadataContactSerializer,
                                           ReferenceSystemDefaultSerializer,
                                           StyleSerializer)
from registry.serializers.security import WebFeatureServiceOperationSerializer
from rest_framework.fields import BooleanField, IntegerField, URLField
from rest_framework_gis.fields import GeometryField
from rest_framework_json_api.relations import (
    ResourceRelatedField, SerializerMethodResourceRelatedField)
from rest_framework_json_api.serializers import (HyperlinkedIdentityField,
                                                 ModelSerializer)


class WebMapServiceOperationUrlSerializer(ModelSerializer):

    # url = HyperlinkedIdentityField(
    #    view_name="registry:wms-operationurls-detail",
    #    read_only=True,
    # )
    service = ResourceRelatedField(
        label=_("web map service"),
        help_text=_(
            "the web map service, where this operation url is part of."),
        read_only=True,
        model=WebMapService,
    )

    class Meta:
        model = WebMapServiceOperationUrl
        fields = "__all__"


class LayerSerializer(
        StringRepresentationSerializer,
        HistoryInformationSerializer,
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
        related_link_url_kwarg="parent_lookup_layer_metadata",
    )

    dataset_metadata = ResourceRelatedField(
        label=_("dataset metadata"),
        help_text=_("related dataset metadata objects"),
        queryset=DatasetMetadataRecord.objects,
        source="registry_datasetmetadatarecord_metadata_records",
        many=True,
        related_link_view_name="registry:layer-datasetmetadata-list",
        related_link_url_kwarg="parent_lookup_self_pointing_layers",
    )
    bbox = GeometryField(
        source="bbox_lat_lon",
        label=_("bbox_l_l"),
        help_text=_("this is the spatial extent of the layer."),
        read_only=True,
    )

    bbox_lat_lon = GeometryField(
        source="bbox_inherited",
        label=_("bbox"),
        help_text=_("this is the spatial extent of the layer."),
        read_only=True,
        auto_bbox=True)

    is_queryable = BooleanField(
        source="is_queryable_inherited",
        label=_("is queryable"),
        read_only=True,
        help_text=_(
            "flag to signal if this layer provides factual information or not."
            " Parsed from capabilities."
        ),
    )
    is_opaque = BooleanField(
        source="is_opaque_inherited",
        label=_("is opaque"),
        read_only=True,
        help_text=_(
            "flag to signal if this layer support transparency content or not. "
            "Parsed from capabilities."
        ),
    )
    is_cascaded = BooleanField(
        source="is_cascaded_inherited",
        label=_("is cascaded"),
        read_only=True,
        help_text=_(
            "WMS cascading allows to expose layers coming from other WMS servers "
            "as if they were local layers"
        ),
    )
    scale_min = IntegerField(
        source="scale_min_inherited",
        label=_("minimal scale"),
        read_only=True,
        help_text=_("the minimum scale value."))
    scale_max = IntegerField(
        source="scale_max_inherited",
        label=_("maximum scale"),
        read_only=True,
        help_text=_("the maximum scale value."))
    styles = SerializerMethodResourceRelatedField(
        label=_("styles"),
        help_text=_("related styles of this layer."),
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
    dimensions = SerializerMethodResourceRelatedField(
        label=_("dimensions"),
        help_text=_("available dimensions of this layer."),
        model=Dimension,
        many=True,
        read_only=True,
    )
    styles = SerializerMethodResourceRelatedField(
        label=_("styles"),
        help_text=_("available styles of this layer."),
        model=Style,
        many=True,
        read_only=True,
    )
    is_spatial_secured = BooleanField(
        label=_("is spatial secured"),
        help_text=_(
            "true is the layer is spatial secured by a allowed operation object."),
        read_only=True
    )

    included_serializers = {
        "service": "registry.serializers.service.WebMapServiceSerializer",
        "service.operation_urls": WebMapServiceOperationUrlSerializer,
        "styles": StyleSerializer,
        "keywords": KeywordSerializer,
        "created_by": UserSerializer,
        "last_modified_by": UserSerializer,
        "reference_systems": ReferenceSystemDefaultSerializer,
        # "dimensions": DimensionSerializer,
    }

    class Meta:
        model = Layer
        fields = "__all__"

    def _collect_inherited_objects(self, instance):
        """Converts the given list of dicts that representing the ReferenceSystem, Dimension and Style objects collected by the manager with ArraySubquery"""
        reference_systems: List[ReferenceSystem] = []
        dimensions: List[Dimension] = []
        styles: List[Style] = []
        for layer in instance.ancestors_include_self:
            for crs in layer.get("reference_systems_inherited", []):
                reference_systems.append(ReferenceSystem(**crs))
            for dimension in layer.get("dimensions_inherited", []):
                dimensions.append(
                    Dimension(**dimension))
            for style in layer.get("styles_inherited", []):
                styles.append(Style(layer=Layer(pk=layer.get("pk")), **style))

        instance.reference_systems_inherited = reference_systems
        instance.dimensions_inherited = dimensions
        instance.styles_inherited = styles

    def get_reference_systems(self, instance):
        if not hasattr(instance, "reference_systems_inherited"):
            self._collect_inherited_objects(instance=instance)
        return instance.reference_systems_inherited

    def get_dimensions(self, instance):
        if not hasattr(instance, "dimensions_inherited"):
            self._collect_inherited_objects(instance=instance)
        return instance.dimensions_inherited

    def get_styles(self, instance):
        if not hasattr(instance, "styles_inherited"):
            self._collect_inherited_objects(instance=instance)
        return instance.styles_inherited


class WebMapServiceListSerializer(
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
        related_link_url_kwarg="parent_lookup_webmapservice_metadata",
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
    proxy_setting = ResourceRelatedField(
        model=WebMapServiceProxySetting,
        related_link_view_name="registry:wms-proxy-settings-list",
        related_link_url_kwarg="parent_lookup_secured_service",
        read_only=True
    )
    camouflage = BooleanField(
        label=_("camouflage"),
        help_text=_(
            "true means the service only accessable via mrmap proxy"),
        read_only=True
    )
    log_response = BooleanField(
        label=_("log response"),
        help_text=_(
            "true means that all responses via mrmap proxy are detected and logged"),
        read_only=True
    )
    is_secured = BooleanField(
        label=_("is secured"),
        help_text=_(
            "true means the service is secured by a allowed operation object."),
        read_only=True
    )
    is_spatial_secured = BooleanField(
        label=_("is spatial secured"),
        help_text=_(
            "true means the service is spatial secured by a allowed operation object."),
        read_only=True
    )

    included_serializers = {
        # we disable including layers on this serializer for now. This will result in slow sql lookups...
        # See comment on github:
        # https://github.com/django/django/pull/5356#issuecomment-1340682072
        # "layers": LayerSerializer,
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


class WebMapServiceSerializer(
    WebMapServiceListSerializer
):

    included_serializers = {
        "layers": LayerSerializer,
        "service_contact": MetadataContactSerializer,
        "metadata_contact": MetadataContactSerializer,
        "keywords": KeywordSerializer,
        "created_by": UserSerializer,
        "last_modified_by": UserSerializer,
        "operation_urls": WebMapServiceOperationUrlSerializer,
    }


class WebMapServiceCreateSerializer(
        ModelSerializer):

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

    # url = SerializerMethodField()

    class Meta:
        model = WebFeatureServiceOperationUrl
        fields = "__all__"

    # def get_url(self, instance):
    #     return instance.get_url(request=self.context["request"])


class FeatureTypeSerializer(
        StringRepresentationSerializer,
        HistoryInformationSerializer,
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
        related_link_url_kwarg="parent_lookup_featuretype_metadata",
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
        "created_by": UserSerializer,
        "last_modified_by": UserSerializer,
        # TODO: "reference_systems": ReferenceSystemDefaultSerializer
    }

    camouflage = BooleanField(
        label=_("camouflage"),
        help_text=_(
            "true means the service only accessable via mrmap proxy"),
        read_only=True
    )
    log_response = BooleanField(
        label=_("log response"),
        help_text=_(
            "true means that all responses via mrmap proxy are detected and logged"),
        read_only=True
    )
    is_secured = BooleanField(
        label=_("is secured"),
        help_text=_(
            "true means the service is secured by a allowed operation object."),
        read_only=True
    )
    is_spatial_secured = BooleanField(
        label=_("is spatial secured"),
        help_text=_(
            "true means the service is spatial secured by a allowed operation object."),
        read_only=True
    )

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
        related_link_url_kwarg="parent_lookup_webfeatureservice_metadata",
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


class WebFeatureServiceCreateSerializer(
        ModelSerializer):
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


class CatalogueServiceOperationUrlSerializer(ModelSerializer):

    # url = SerializerMethodField()

    class Meta:
        model = CatalogueServiceOperationUrl
        fields = "__all__"

    # def get_url(self, instance):
    #     return instance.get_url(request=self.context["request"])


class CatalogueServiceCreateSerializer(
        ModelSerializer):
    get_capabilities_url = URLField(validators=[validate_get_capablities_uri])
    service_auth = ResourceRelatedField(
        queryset=WebFeatureServiceAuthentication.objects, required=False
    )
    owner = ResourceRelatedField(queryset=Organization.objects)

    class Meta:
        model = CatalogueService
        fields = (
            "get_capabilities_url",
            "owner",
            "service_auth",
        )


class CatalogueServiceSerializer(
        StringRepresentationSerializer,
        HistoryInformationSerializer,
        ModelSerializer):
    url = HyperlinkedIdentityField(
        view_name="registry:csw-detail",
    )
    harvested_dataset_count = IntegerField(read_only=True)
    harvested_service_count = IntegerField(read_only=True)
    harvested_total_count = IntegerField(read_only=True)
    # TODO: deprecated;
    # use distinct query over harvesting_jobs__registry_harvesteddatasetmetadatarelations__dataset_metadata_record.distinct()
    # registry_datasetmetadatarecord
    harvesting_jobs = ResourceRelatedField(
        model=HarvestingJob,
        many=True,
        read_only=True,
        # related_link_view_name="registry:csw-datasetmetadata-list",
        # related_link_url_kwarg="parent_lookup_harvested_through",
    )
    running_harvesting_job = SerializerMethodResourceRelatedField(
        model=HarvestingJob,
        read_only=True
    )
    service_contact = ResourceRelatedField(
        queryset=MetadataContact.objects,
        related_link_view_name="registry:csw-service-contact-list",
        related_link_url_kwarg="parent_lookup_service_contact_catalogueservice_metadata",
    )
    metadata_contact = ResourceRelatedField(
        queryset=MetadataContact.objects,
        related_link_view_name="registry:csw-metadata-contact-list",
        related_link_url_kwarg="parent_lookup_metadata_contact_catalogueservice_metadata",
    )
    keywords = ResourceRelatedField(
        queryset=Keyword.objects,
        many=True,
        related_link_view_name="registry:csw-keywords-list",
        related_link_url_kwarg="parent_lookup_catalogueservice_metadata",
    )
    operation_urls = ResourceRelatedField(
        label=_("operation urls"),
        help_text=_("this are the urls to use for the ogc operations."),
        model=CatalogueServiceOperationUrl,
        many=True,
        read_only=True,
    )
    periodic_harvesting_jobs = ResourceRelatedField(
        label=_("periodic harvesting jobs"),
        help_text=_("this are the related harvesting job objects."),
        model=PeriodicHarvestingJob,
        many=True,
        read_only=True,
    )

    included_serializers = {
        "harvesting_jobs": 'registry.serializers.harvesting.HarvestingJobSerializer',
        "service_contact": MetadataContactSerializer,
        "metadata_contact": MetadataContactSerializer,
        "keywords": KeywordSerializer,
        "created_by": UserSerializer,
        "last_modified_by": UserSerializer,
        "operation_urls": CatalogueServiceOperationUrlSerializer,
    }

    class Meta:
        model = CatalogueService
        fields = "__all__"

    def get_running_harvesting_job(self, instance):
        if hasattr(instance, "running_harvesting_job") and instance.running_harvesting_job.__len__() == 1:
            return instance.running_harvesting_job[0]
