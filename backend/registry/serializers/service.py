from datetime import datetime

from accounts.models.groups import Organization
from accounts.serializers.groups import OrganizationSerializer
from accounts.serializers.users import UserSerializer
from accounts.utils import organizations_of
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema_field
from extras.permissions import Visibility
from extras.serializers import (HistoryInformationSerializer,
                                ObjectPermissionCheckerSerializer,
                                StringRepresentationSerializer,
                                SystemInfoSerializerMixin)
from extras.validators import validate_get_capablities_uri
from lxml.etree import XMLSyntaxError
from registry.helper.resource_capabilities import (
    feature_type_capabilities_url, layer_capabilities_url)
from registry.models.harvest import HarvestingJob, PeriodicHarvestingJob
from registry.models.metadata import (DatasetMetadataRecord, Keyword,
                                      MetadataContact, ReferenceSystem, Style,
                                      TimeExtent)
from registry.models.monitoring import (CatalogueServiceMonitoringSetting,
                                        WebFeatureServiceMonitoringSetting,
                                        WebMapServiceMonitoringSetting)
from registry.models.security import (AllowedWebMapServiceOperation,
                                      WebFeatureServiceAuthentication,
                                      WebMapServiceAuthentication,
                                      WebMapServiceProxySetting)
from registry.models.service import (CatalogueService,
                                     CatalogueServiceOperationUrl, FeatureType,
                                     Layer, WebFeatureService,
                                     WebFeatureServiceOperationUrl,
                                     WebMapService, WebMapServiceOperationUrl)
from registry.models.update import WebMapServiceUpdateSetting
from registry.ows_lib.client.exceptions import InitialError
from registry.ows_lib.wms.wms import WebMapServiceClient
from registry.querys.alerts import SERVICE_KIND_OF
from registry.serializers.metadata import (KeywordSerializer,
                                           MetadataContactSerializer,
                                           MimeTypeSerializer,
                                           ReferenceSystemDefaultSerializer,
                                           StyleSerializer,
                                           TimeExtentSerializer)
from registry.serializers.security import WebFeatureServiceOperationSerializer
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.fields import (BooleanField, ChoiceField, DateTimeField,
                                   IntegerField, SerializerMethodField,
                                   URLField)
from rest_framework.reverse import reverse
from rest_framework_gis.fields import GeometryField
from rest_framework_json_api.relations import (
    ResourceRelatedField, SerializerMethodResourceRelatedField)
from rest_framework_json_api.serializers import (HyperlinkedIdentityField,
                                                 ModelSerializer)


#: the read-only answer of the stored owner of #733, one text for the three
#: service serializers that expose it
OWNER_HELP_TEXT = _(
    "the organization which owns this service; empty on services "
    "registered before ownership was stored")


class WebMapServiceOperationUrlSerializer(SystemInfoSerializerMixin, ModelSerializer):

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


class ServiceElementHistoryInformationSerializer(HistoryInformationSerializer):
    def get_created_at(self, instance) -> datetime:
        # Legacy bulk registrations have no child creation record. The service
        # registration date is an estimate; do not manufacture historical rows.
        created_at = super().get_created_at(instance)
        return created_at if created_at is not None else getattr(instance, 'service_created_at', None)


IS_SECURED_LABEL = _("is secured")

IS_SPATIAL_SECURED_LABEL = _("is spatial secured")


class LayerSerializer(
        StringRepresentationSerializer,
        ServiceElementHistoryInformationSerializer,
        SystemInfoSerializerMixin,
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
        source="bbox_lat_lon_inherited",
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
    reference_systems = SerializerMethodResourceRelatedField(
        label=_("reference systems"),
        help_text=_("available reference systems of this layer."),
        model=ReferenceSystem,
        many=True,
        read_only=True,
    )
    time_extents = SerializerMethodResourceRelatedField(
        label=_("time extents"),
        help_text=_("available time extents of this layer."),
        model=TimeExtent,
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
    is_secured = BooleanField(label=IS_SECURED_LABEL, read_only=True)
    is_spatial_secured = BooleanField(
        label=IS_SPATIAL_SECURED_LABEL,
        help_text=_(
            "true is the layer is spatial secured by a allowed operation object."),
        read_only=True
    )
    capabilities_url = SerializerMethodField(
        label=_("capabilities url"),
        help_text=_(
            "the url of the capabilities document which advertises only this layer."),
        read_only=True,
    )

    included_serializers = {
        "service": "registry.serializers.service.WebMapServiceSerializer",
        "service.operation_urls": WebMapServiceOperationUrlSerializer,
        "styles": StyleSerializer,
        "keywords": KeywordSerializer,
        "created_by": UserSerializer,
        "last_modified_by": UserSerializer,
        "reference_systems": ReferenceSystemDefaultSerializer,
        "time_extents": TimeExtentSerializer,
        # "dimensions": DimensionSerializer,
    }

    class Meta:
        model = Layer
        fields = "__all__"

    def _convert_dict_to_object(self, objs, model_cls, defaults={}):
        if objs and isinstance(objs, list) and isinstance(objs[0], dict):
            return [model_cls(**defaults, **obj) for obj in objs]
        return objs

    def get_reference_systems(self, instance):
        return self._convert_dict_to_object(getattr(instance, "reference_systems_inherited", []), ReferenceSystem)

    def get_time_extents(self, instance):
        return self._convert_dict_to_object(getattr(instance, "time_extents_inherited", []), TimeExtent)

    def get_styles(self, instance):
        return self._convert_dict_to_object(getattr(instance, "styles_inherited", []), Style, defaults={"layer": Layer(pk=instance.pk)})

    @extend_schema_field({"type": "string", "format": "uri"})
    def get_capabilities_url(self, instance) -> str:
        # The capabilities document of a single layer is generated for every request
        # out of the registry (registry/proxy/resource_capabilities.py) and is never
        # stored, so the url of it is named by the layer of this answer alone:
        # neither the service nor its capabilities are read here.
        return layer_capabilities_url(
            instance.pk, request=self.context.get("request"))


class ServiceAlertSerializerMixin(ModelSerializer):
    """Answers the states of a service which an administrator has to attend to.

    The states are annotated to the queryset of the services by
    registry/querys/alerts.py, which means that they are filterable, sortable and
    countable like any other attribute of a service - and that the viewset which
    answers them decides whether they are annotated at all, because they are
    answered by a subquery per attribute.

    The schedules a service did not keep are not answered here, because a
    crontab is no rule of the database: a client reads them from the monitoring
    and update settings of the service, which answer their `runOverdue`.

    Next to the states themselves the mixin answers *which* run or job decided a
    state: `monitoring_failed_run`, `update_failed_job` and `update_review_job`
    are relationships to the rows behind the alerts of the same name. These
    references are additive - a client which ignores them reads the same alerts
    as before - and they name a record of its own kind, so that a client which
    may view it reads it at the endpoint of that kind and a client which may not
    view it is answered nothing but the alert of its own service. A reference is
    answered by the very subquery which decides the alert next to it, so that a
    state and its reference can never disagree, and a list reads the rows behind
    the references of its page with `registry.querys.alerts.alert_records()`.
    """

    has_alert = BooleanField(
        label=_("has alert"),
        help_text=_("true if any state of the service needs attention"),
        read_only=True)

    monitoring_failed = BooleanField(
        label=_("monitoring failed"),
        help_text=_(
            "true if the last monitoring run of the service reported a failure"),
        read_only=True)
    monitoring_failed_at = DateTimeField(
        label=_("monitoring failed at"),
        help_text=_(
            "the point in time the last monitoring run of the service was done"),
        read_only=True)

    update_review_required = BooleanField(
        label=_("update review required"),
        help_text=_(
            "true if an update of the service waits for a decision about it"),
        read_only=True)
    update_review_required_at = DateTimeField(
        label=_("update review required at"),
        help_text=_(
            "the point in time the update which waits for a decision was made"),
        read_only=True)
    update_failed = BooleanField(
        label=_("update failed"),
        help_text=_(
            "true if the last update of the service came back broken"),
        read_only=True)
    update_failed_at = DateTimeField(
        label=_("update failed at"),
        help_text=_(
            "the point in time the last update of the service was made"),
        read_only=True)

    def get_fields(self):
        """Answer the references of the alerts as relationships of the kind

        The row behind an alert belongs to a model of the kind of the service,
        so the fields which reference it are built from the kind of `Meta.model`
        here instead of being declared on the mixin itself.
        """
        fields = super().get_fields()
        kind = SERVICE_KIND_OF[self.Meta.model]
        fields['monitoring_failed_run'] = SerializerMethodResourceRelatedField(
            label=_("monitoring failed run"),
            help_text=_(
                "the monitoring run which reported the failure, answered as its "
                "identifier and nothing if the service needs no attention in "
                "monitoring"),
            model=kind.monitoring_run,
            read_only=True)
        fields['update_review_job'] = SerializerMethodResourceRelatedField(
            label=_("update review job"),
            help_text=_(
                "the update job which waits for a decision, answered as its "
                "identifier and nothing if the service waits for a decision "
                "because of a dangling update candidate only"),
            model=kind.update_job,
            read_only=True)
        fields['update_failed_job'] = SerializerMethodResourceRelatedField(
            label=_("update failed job"),
            help_text=_(
                "the update job which came back broken, answered as its identifier "
                "and nothing if the last update of the service did not fail"),
            model=kind.update_job,
            read_only=True)
        return fields

    def alert_record(self, model, identifier):
        """The row behind a reference of an alert, if there is one

        A list of services reads the rows of its page at once, see
        `registry.querys.alerts.alert_records()`; a single service reads its row
        alone, which is one query per reference of one service.

        Args:
            model: the model of the rows to look in
            identifier: the identifier which the annotation answered, optional

        Returns:
            the row behind the reference, None if the alert answers none
        """
        if identifier is None:
            return None
        records = self.context.get('alert_records')
        if records is None:
            return model.objects.filter(pk=identifier).first()
        return records.get(model, {}).get(identifier)

    def get_monitoring_failed_run(self, instance):
        return self.alert_record(
            SERVICE_KIND_OF[self.Meta.model].monitoring_run,
            getattr(instance, 'monitoring_failed_run', None))

    def get_update_review_job(self, instance):
        return self.alert_record(
            SERVICE_KIND_OF[self.Meta.model].update_job,
            getattr(instance, 'update_review_job', None))

    def get_update_failed_job(self, instance):
        return self.alert_record(
            SERVICE_KIND_OF[self.Meta.model].update_job,
            getattr(instance, 'update_failed_job', None))

    class Meta:
        abstract = True


class VisibilityField(ChoiceField):
    """The tri-state answer of #739, read from the queryset's annotation.

    The list annotates ``visibility`` over guardian's tables in its own SELECT,
    so a page answers the field without a query per row. A serializer which
    gets an object of a queryset that did not annotate it - an included service
    of a layer list, a future relation - omits the attribute, exactly like
    :class:`ServiceAlertSerializerMixin` omits an alert state it was not given:
    the answer belongs to the query which decided to answer it, and a field
    which asked one query per row there is the growth
    ``tests/django/registry/tests_query_performance.py`` refuses.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault('choices', Visibility.choices)
        # the answer is derived from the grants of the resource, so a client
        # never has to know it: only a PATCH which deliberately moves the
        # resource across the public axis names the field at all
        kwargs.setdefault('required', False)
        super().__init__(**kwargs)


class VisibilitySerializerMixin(ModelSerializer):
    """Answers and writes the visibility tri-state of a service (#739).

    The read is the annotation; the write is one axis only: a PATCH which
    names ``public`` gives the anonymous view grant to the anonymous viewer
    role group and a PATCH which names ``organization-internal`` takes it
    back. Publishing is the act of the ``publish_resource`` permission;
    withdrawing from the public is the same act reversed and additionally
    allowed for whoever manages the resource's access rules.

    ``restricted`` is never writable: it is the absence of both the public
    grant and the organization-wide one, and shaping it deliberately is the
    sharing surface of #740, not a detail of this endpoint.

    The base is ``ModelSerializer`` and not ``object``, like
    :class:`ServiceAlertSerializerMixin`: DRF collects the declared fields of a
    class through its metaclass, so a field declared on a plain mixin is never
    seen - the same lesson #1267 records for the ownership field.
    """

    visibility = VisibilityField(
        label=_("visibility"),
        help_text=_(
            "who may see this resource: public means anonymous visitors "
            "hold the view permission, organization-internal means a role of "
            "the owning organization does - the state every new resource "
            "starts in - and restricted means neither; only public and "
            "organization-internal are writable"))

    def update(self, instance, validated_data):
        """Writes the asked visibility, or nothing at all.

        The request is decided before the first write: the endpoint answers
        400 or 403 without touching the resource, because there is no
        transaction around a PATCH which would undo the other attributes of
        the very same request after the visibility was refused.
        """
        requested = validated_data.pop('visibility', None)
        if requested is not None:
            self.check_visibility_write(instance, requested)
        instance = super().update(instance, validated_data)
        if requested is not None:
            self.apply_visibility(instance, requested)
        return instance

    @staticmethod
    def current_visibility(instance):
        """The answered state of one resource, asked with the list's own SQL.

        The write path needs the state which is, and the representation of the
        object it just changed needs the state which now is. Both ask the very
        expression the list annotates, for exactly one row, so a decision and
        the answer about it cannot disagree.
        """
        return instance.__class__.objects.filter(
            pk=instance.pk).with_visibility().values_list(
                'visibility', flat=True).first()

    def check_visibility_write(self, instance, requested):
        """Refuse a visibility a caller may not write, before anything is sent.

        Raises:
            ValidationError: ``restricted`` (never writable) or the withdrawal
                of a resource which is not public
            PermissionDenied: the caller holds neither the publish permission
                nor, for the way back, the management of the access rules
        """
        from extras.permissions import allowed

        app = instance._meta.app_label
        user = getattr(self.context.get('request'), 'user', None)

        if requested == Visibility.PUBLIC:
            if not allowed(user, f'{app}.publish_resource', instance):
                raise PermissionDenied(
                    _('The publish permission of this resource is required '
                      'to make it public.'))
        elif requested == Visibility.ORGANIZATION_INTERNAL:
            if self.current_visibility(instance) != Visibility.PUBLIC.value:
                raise ValidationError({
                    'visibility': _(
                        'Only a public resource can be withdrawn from the '
                        'public; the remaining grants of a resource are '
                        'managed by the sharing of access rules.')})
            if not (allowed(user, f'{app}.publish_resource', instance)
                    or allowed(user, f'{app}.manage_access_rules',
                               instance)):
                raise PermissionDenied(
                    _('The publish permission or the management of the '
                      'access rules of this resource is required to withdraw '
                      'it from the public.'))
        else:
            raise ValidationError({
                'visibility': _(
                    'restricted is answered by the grants a resource does '
                    'not carry; it is not writable here.')})

    def apply_visibility(self, instance, requested):
        """Move the resource across the public axis, the request being decided."""
        from extras.permissions import set_public

        set_public(instance, requested == Visibility.PUBLIC.value)
        # the annotation the request read is as old as the request; the
        # representation of the resource which just moved asks its own answer,
        # so the payload names the new state and not the one before it
        instance.visibility = self.current_visibility(instance)


@extend_schema_field({
    'type': 'object',
    'format': 'geojson',
    'nullable': True,
    'properties': {
        'type': {'type': 'string', 'enum': ['Polygon', 'MultiPolygon']},
        'coordinates': {'type': 'array', 'items': {}},
    },
    'required': ['type', 'coordinates'],
})
class ServiceExtentField(GeometryField):
    pass


class ExplorerAttributesSerializer(ObjectPermissionCheckerSerializer):
    extent = ServiceExtentField(read_only=True)
    element_count = IntegerField(read_only=True)

    def explorer_fields(self):
        request = self.context.get('request')
        from rest_framework_json_api.utils import undo_format_field_name
        return [undo_format_field_name(name.strip()) for name in
                request.GET.get(f'fields[{self.Meta.model.__name__}]', '').split(',')] if request else []

    def answers_allowed_actions(self) -> bool:
        """Whether ``allowed_actions`` belongs to this representation.

        A request that narrows this resource type with a sparse fieldset
        gets the hint exactly when it names it - the opt-in rule of
        ``extent`` and ``element_count``, kept for the permission hint by
        #738, which also short-circuits ``get_allowed_actions`` so the value
        is not computed for a renderer that would drop it. A request without
        any fieldset for this type answers the hint unasked on the detail
        endpoint and not on a list: a list of a deployment's services is not
        paid for by screens that do not read the hint.
        """
        request = self.context.get('request')
        if request is None:
            return False
        key = f'fields[{self.Meta.model.__name__}]'
        if key in request.GET:
            return 'allowed_actions' in self.explorer_fields()
        return getattr(self.context.get('view'), 'action', None) != 'list'

    def to_representation(self, instance):
        result = super().to_representation(instance)
        requested = self.explorer_fields()
        for name in ('extent', 'element_count'):
            if name not in requested:
                result.pop(name, None)
        if not self.answers_allowed_actions():
            result.pop('allowed_actions', None)
        return result

    def get_allowed_actions(self, obj) -> list:
        if not self.answers_allowed_actions():
            return []
        # the facade answers the whole action batch with the checker of the
        # request: the role axes once per request and app, the object axis
        # from the page the viewset already prefetched (#734, #738)
        return super().get_allowed_actions(obj)


MONITORING_SETTINGS_HELP_TEXT = _("This are the configured monitoring settings.")

MONITORING_SETTINGS_LABEL = _("monitoring settings")

OPERATION_URLS_HELP_TEXT = _("this are the urls to use for the ogc operations.")

OPERATION_URLS_LABEL = _("operation urls")


class WebMapServiceListSerializer(
    ServiceAlertSerializerMixin,
    VisibilitySerializerMixin,
    ExplorerAttributesSerializer,
    StringRepresentationSerializer,
    HistoryInformationSerializer,
    SystemInfoSerializerMixin,
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
        model=AllowedWebMapServiceOperation,
        many=True,
        related_link_view_name="registry:wms-allowedwmsoperation-list",
        related_link_url_kwarg="parent_lookup_secured_service",
        read_only=True
    )
    operation_urls = ResourceRelatedField(
        label=OPERATION_URLS_LABEL,
        help_text=OPERATION_URLS_HELP_TEXT,
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
        label=IS_SECURED_LABEL,
        help_text=_(
            "true means the service is secured by a allowed operation object."),
        read_only=True
    )
    is_spatial_secured = BooleanField(
        label=IS_SPATIAL_SECURED_LABEL,
        help_text=_(
            "true means the service is spatial secured by a allowed operation object."),
        read_only=True
    )
    xml_backup_file_secured = SerializerMethodField(
        label=_("secured xml backup file"),
        help_text=_(
            "the original xml backup file as secured url to restore the xml field."),
        read_only=True,
    )
    web_map_service_monitoring_settings = ResourceRelatedField(
        source="web_map_service_monitorings",
        label=MONITORING_SETTINGS_LABEL,
        help_text=MONITORING_SETTINGS_HELP_TEXT,
        model=WebMapServiceMonitoringSetting,
        many=True,
        read_only=True,
    )
    web_map_service_update_settings = ResourceRelatedField(
        label=_("update settings"),
        help_text=_("This are the configured update settings."),
        model=WebMapServiceUpdateSetting,
        many=True,
        read_only=True,
    )
    preview_url = SerializerMethodField(
        label=_("preview url"),
        help_text=_("the url to the preview image of the service."),
        read_only=True,
    )
    # the stored owner of #733, answered read-only: the relation is decided
    # at creation by the create serializer's validation and is not writable
    # through the update of a service
    owner = ResourceRelatedField(
        model=Organization,
        read_only=True,
        label=_("owner"),
        help_text=OWNER_HELP_TEXT)

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
        "owner": OrganizationSerializer,
    }

    class Meta:
        model = WebMapService
        fields = "__all__"

    def get_xml_backup_file_secured(self, instance):
        request = self.context.get("request")
        return instance.get_secured_capabilities_url(request=request)

    @extend_schema_field({"type": "string", "format": "uri"})
    def get_preview_url(self, instance) -> str | None:
        # The preview image is asked by the details of a service and by the details
        # panel beside the list of the services, so both serializers answer it. It is
        # read from the stored capabilities only: a preview never needs more than the
        # document the registry holds, and since #1044 the read of Service.capabilities
        # answers that stored document or raises - a service whose file is gone from
        # the storage simply has no preview here. A json:api request which doesn't name
        # the attribute in its sparse fieldset never constructs it, so a list which
        # doesn't show a preview doesn't pay for it. A service without capabilities
        # that can describe a preview simply has none.
        if not instance.xml_backup_file:
            return None
        try:
            capabilities = instance.xml_backup
        except FileNotFoundError:
            return None
        try:
            return WebMapServiceClient(capabilities=capabilities).get_preview_request().url
        except (XMLSyntaxError, InitialError, ValueError):
            return None


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
        "owner": OrganizationSerializer,
    }


class OrganizationOwnerCreateSerializerMixin:
    """The `owner` relation of a create, validated against the creating user.

    Before #733 this relation was answered and thrown away: the create
    serializers declared it, the task which persists the resource never saw
    it, and a client could name any organization as the owner of a service
    while the service stayed ownerless. The accepted shape of #727 (Q3=A)
    stores the owner as a typed foreign key, so this mixin decides - at
    creation time and server-side - which organization the stored owner is:

    * a client which names an owner may name only an organization the
      creating user is a member of; a superuser may name any organization,
      as the superuser holds every permission of every organization,
    * a client which names no owner gets the creating user's only
      organization - and a user with no membership or with more than one
      gets a validation error instead of a guess, because defaulting to the
      first membership or to an unrelated organization is exactly what
      Q3=A forbids.

    The decided owner travels to the task through the viewset's
    `get_task_kwargs` and is written by the task, which is where the
    resource row comes into the world.

    A serializer using this mixin must declare its own `owner` field from
    `OWNERSHIP_FIELD_KWARGS`: DRF collects declared fields from the
    serializer's own body and from serializer bases, not from plain
    mixins - without its own declaration the name falls through to the
    model field, which is `editable=False` and therefore generates
    read-only.
    """

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        organizations = organizations_of(user)

        owner = attrs.get("owner")
        if owner is not None:
            if user is not None and user.is_superuser:
                return attrs
            if not organizations.filter(pk=owner.pk).exists():
                raise ValidationError({
                    "owner": _(
                        "The creating user is not a member of the selected "
                        "organization. A resource can only be registered "
                        "for an organization the creating user is a member "
                        "of.")})
            return attrs

        # no owner named: only an unambiguous single membership may decide
        if user is not None and user.is_superuser:
            raise ValidationError({
                "owner": _(
                    "The owner relation is required: the creating user's "
                    "memberships do not answer one owning organization.")})
        memberships = list(organizations[:2])
        if len(memberships) == 1:
            attrs["owner"] = memberships[0]
            return attrs
        if not memberships:
            raise ValidationError({
                "owner": _(
                    "The creating user is not member of any organization. "
                    "The owner relation must name the organization which "
                    "shall own the registered service.")})
        raise ValidationError({
            "owner": _(
                "The creating user is member of more than one organization. "
                "The owner relation must name the organization which shall "
                "own the registered service.")})


#: the client-facing words of the create relation, one answer for the three
#: resource kinds so that schema and dialog name the concept identically
#: (#1267) - unpacked into each create serializer's own `owner` declaration
OWNERSHIP_FIELD_KWARGS = {
    "queryset": Organization.objects,
    "required": False,
    "label": _("owner"),
    "help_text": _(
        "The organization which owns the registered service and grants all "
        "rights on it. Required when the creating user belongs to more than "
        "one organization; the creating user must be a member of an "
        "organization named here."),
}


class WebMapServiceCreateSerializer(
    OrganizationOwnerCreateSerializerMixin,
    SystemInfoSerializerMixin,
        ModelSerializer):

    get_capabilities_url = URLField(
        label=_("get capabilities url"),
        help_text=_("a valid get capabilities url."),
        validators=[validate_get_capablities_uri])
    service_auth = ResourceRelatedField(
        queryset=WebMapServiceAuthentication.objects,
        required=False,
        label=_("authentication credentials"),
        help_text=_("Optional authentication credentials to request the remote service."))
    # the validation of this relation is the mixin's; the declaration lives
    # here because DRF only collects fields of the serializer's own body
    owner = ResourceRelatedField(**OWNERSHIP_FIELD_KWARGS)
    # default True is kept on purpose (#1264): turning it off would change
    # registration behaviour for every existing client
    collect_metadata_records = BooleanField(
        default=True,
        label=_("collect metadata records"),
        help_text=_(
            "If checked, Mr. Map collects the metadata documents referenced by "
            "the capabilities document after the registration task. A document "
            "which cannot be reached is reported as a failed metadata "
            "reference in the background jobs, where it can be retried."))

    class Meta:
        model = WebMapService
        fields = (
            "get_capabilities_url",
            "owner",
            "service_auth",
            "collect_metadata_records",
        )


class WebFeatureServiceOperationUrlSerializer(SystemInfoSerializerMixin, ModelSerializer):

    class Meta:
        model = WebFeatureServiceOperationUrl
        fields = "__all__"


class FeatureTypeSerializer(
        StringRepresentationSerializer,
        ServiceElementHistoryInformationSerializer,
        SystemInfoSerializerMixin,
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

    dataset_metadata = ResourceRelatedField(
        label=_("dataset metadata"),
        help_text=_("related dataset metadata objects"),
        model=DatasetMetadataRecord,
        source="registry_datasetmetadatarecord_metadata_records",
        many=True,
        read_only=True,
        related_link_view_name="registry:featuretype-datasetmetadata-list",
        related_link_url_kwarg="parent_lookup_self_pointing_feature_types",
    )

    metadata_references_uncollected = BooleanField(
        label=_("metadata references uncollected"),
        help_text=_(
            "true means the capabilities of this feature type reference metadata "
            "documents while no dataset metadata record is linked to it: the "
            "references were not collected. This is the state of a service "
            "registered before feature type references were collected (#1257) "
            "and of a collection whose references all failed; a single linked "
            "record answers false."
        ),
        read_only=True,
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
        "dataset_metadata": "registry.serializers.metadata.DatasetMetadataRecordSerializer",
        "created_by": UserSerializer,
        "last_modified_by": UserSerializer,
        "reference_systems": ReferenceSystemDefaultSerializer,
        "default_reference_system": ReferenceSystemDefaultSerializer,
        "output_formats": MimeTypeSerializer,
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
        label=IS_SECURED_LABEL,
        help_text=_(
            "true means the service is secured by a allowed operation object."),
        read_only=True
    )
    is_spatial_secured = BooleanField(
        label=IS_SPATIAL_SECURED_LABEL,
        help_text=_(
            "true means the service is spatial secured by a allowed operation object."),
        read_only=True
    )
    capabilities_url = SerializerMethodField(
        label=_("capabilities url"),
        help_text=_(
            "the url of the capabilities document which advertises only this featuretype."),
        read_only=True,
    )

    @extend_schema_field({"type": "string", "format": "uri"})
    def get_capabilities_url(self, instance) -> str:
        # The capabilities document of a single featuretype is generated for every
        # request out of the registry (registry/proxy/resource_capabilities.py) and is
        # never stored, so the url of it is named by the featuretype of this answer
        # alone: neither the service nor its capabilities are read here.
        return feature_type_capabilities_url(
            instance.pk, request=self.context.get("request"))

    class Meta:
        model = FeatureType
        fields = "__all__"


class WebFeatureServiceSerializer(
        ServiceAlertSerializerMixin,
        VisibilitySerializerMixin,
        ExplorerAttributesSerializer,
        StringRepresentationSerializer,
        HistoryInformationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name="registry:wfs-detail",
    )
    preview_url = SerializerMethodField(
        label=_("preview image"), read_only=True)

    @extend_schema_field({"type": "string", "format": "uri"})
    def get_preview_url(self, instance) -> str | None:
        return reverse("registry:wfs-preview-image", kwargs={"pk": instance.pk},
                       request=self.context.get("request"))

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
        label=OPERATION_URLS_LABEL,
        help_text=OPERATION_URLS_HELP_TEXT,
        model=WebFeatureServiceOperationUrl,
        many=True,
        read_only=True,
    )
    # the stored owner of #733; decided at creation, not writable here
    owner = ResourceRelatedField(
        model=Organization,
        read_only=True,
        label=_("owner"),
        help_text=OWNER_HELP_TEXT)

    web_feature_service_monitoring_settings = ResourceRelatedField(
        source="web_feature_service_monitorings",
        label=MONITORING_SETTINGS_LABEL,
        help_text=MONITORING_SETTINGS_HELP_TEXT,
        model=WebFeatureServiceMonitoringSetting,
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
        "owner": OrganizationSerializer,
    }

    class Meta:
        model = WebFeatureService
        fields = "__all__"


class WebFeatureServiceCreateSerializer(
        OrganizationOwnerCreateSerializerMixin,
        SystemInfoSerializerMixin,
        ModelSerializer):
    get_capabilities_url = URLField(validators=[validate_get_capablities_uri])
    service_auth = ResourceRelatedField(
        queryset=WebFeatureServiceAuthentication.objects, required=False
    )
    # the validation of this relation is the mixin's; the declaration lives
    # here because DRF only collects fields of the serializer's own body -
    # with the WMS' words, one word per concept (#1267)
    owner = ResourceRelatedField(**OWNERSHIP_FIELD_KWARGS)

    # the same option the WMS create offers: one word per concept means the
    # very same msgids here, so both languages name it identically (#1267);
    # the text says what is collected, what a failure does and where to look
    # (#1264)
    collect_metadata_records = BooleanField(
        default=True,
        label=_("collect metadata records"),
        help_text=_(
            "If checked, Mr. Map collects the metadata documents referenced by "
            "the capabilities document after the registration task. A document "
            "which cannot be reached is reported as a failed metadata "
            "reference in the background jobs, where it can be retried."))

    class Meta:
        model = WebFeatureService
        fields = (
            "get_capabilities_url",
            "owner",
            "service_auth",
            "collect_metadata_records",
        )


class CatalogueServiceOperationUrlSerializer(SystemInfoSerializerMixin, ModelSerializer):

    class Meta:
        model = CatalogueServiceOperationUrl
        fields = "__all__"


class CatalogueServiceCreateSerializer(
        OrganizationOwnerCreateSerializerMixin,
        SystemInfoSerializerMixin,
        ModelSerializer):
    get_capabilities_url = URLField(validators=[validate_get_capablities_uri])
    service_auth = ResourceRelatedField(
        queryset=WebFeatureServiceAuthentication.objects, required=False
    )
    # the validation of this relation is the mixin's; the declaration lives
    # here because DRF only collects fields of the serializer's own body
    owner = ResourceRelatedField(**OWNERSHIP_FIELD_KWARGS)

    class Meta:
        model = CatalogueService
        fields = (
            "get_capabilities_url",
            "owner",
            "service_auth",
        )


class CatalogueServiceSerializer(
        ServiceAlertSerializerMixin,
        ExplorerAttributesSerializer,
        StringRepresentationSerializer,
        HistoryInformationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):
    is_harvestable = BooleanField(read_only=True)
    url = HyperlinkedIdentityField(
        view_name="registry:csw-detail",
    )
    harvested_dataset_count = IntegerField(read_only=True)
    harvested_service_count = IntegerField(read_only=True)
    harvested_total_count = IntegerField(read_only=True)
    harvest_aborted = BooleanField(
        label=_("harvest aborted"),
        help_text=_(
            "true if the last harvesting job of the catalogue ended before it "
            "was done"),
        read_only=True)
    harvest_incomplete = BooleanField(
        label=_("harvest incomplete"),
        help_text=_(
            "true if the last harvesting job of the catalogue left records "
            "behind - records it could not import into the registry or records "
            "its pages did not deliver"),
        read_only=True)
    harvest_failed_at = DateTimeField(
        label=_("harvest failed at"),
        help_text=_(
            "the point in time the last harvesting job of the catalogue was "
            "made"),
        read_only=True)
    harvest_job = SerializerMethodResourceRelatedField(
        label=_("harvest job"),
        help_text=_(
            "the harvesting job of the catalogue which ended before it was done "
            "or which left records behind, answered as its identifier and "
            "nothing if the last harvesting of the catalogue needs no "
            "attention"),
        model=HarvestingJob,
        read_only=True)
    # FUTURE: deprecated;
    # use distinct query over harvesting_jobs__registry_harvesteddatasetmetadatarelations__dataset_metadata_record.distinct()
    # registry_datasetmetadatarecord
    harvesting_jobs = ResourceRelatedField(
        model=HarvestingJob,
        many=True,
        read_only=True,
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
        label=OPERATION_URLS_LABEL,
        help_text=OPERATION_URLS_HELP_TEXT,
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
    catalogue_service_monitoring_settings = ResourceRelatedField(
        source="catalogue_service_monitorings",
        label=MONITORING_SETTINGS_LABEL,
        help_text=MONITORING_SETTINGS_HELP_TEXT,
        model=CatalogueServiceMonitoringSetting,
        many=True,
        read_only=True,
    )
    # the stored owner of #733; decided at creation, not writable here
    owner = ResourceRelatedField(
        model=Organization,
        read_only=True,
        label=_("owner"),
        help_text=OWNER_HELP_TEXT)

    included_serializers = {
        "harvesting_jobs": 'registry.serializers.harvesting.HarvestingJobSerializer',
        "service_contact": MetadataContactSerializer,
        "metadata_contact": MetadataContactSerializer,
        "keywords": KeywordSerializer,
        "created_by": UserSerializer,
        "last_modified_by": UserSerializer,
        "operation_urls": CatalogueServiceOperationUrlSerializer,
        "owner": OrganizationSerializer,
    }

    class Meta:
        model = CatalogueService
        fields = "__all__"

    def get_running_harvesting_job(self, instance):
        if hasattr(instance, "running_harvesting_job") and instance.running_harvesting_job.__len__() == 1:
            return instance.running_harvesting_job[0]

    def get_harvest_job(self, instance):
        return self.alert_record(
            HarvestingJob, getattr(instance, 'harvest_job', None))


class CatalogueServiceOperationUrlSerializer(SystemInfoSerializerMixin, ModelSerializer):

    service = ResourceRelatedField(
        label=_("catalogue service"),
        help_text=_(
            "the catalogue service, where this operation url is part of."),
        read_only=True,
        model=CatalogueService,
    )

    class Meta:
        model = CatalogueServiceOperationUrl
        fields = "__all__"
