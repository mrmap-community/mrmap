from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from django.conf import settings
from django.contrib.gis.db import models
from django.contrib.gis.db import models as gis_models
from django.contrib.gis.geos import Polygon
from django.db.models import QuerySet
from django.urls import NoReverseMatch, reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from eulxml import xmlmap
from extras.managers import DefaultHistoryManager
from extras.models import HistoricalRecordMixin
from extras.utils import update_url_base, update_url_query_params
from mptt.models import MPTTModel, TreeForeignKey
from MrMap.settings import PROXIES
from ows_lib.client.utils import get_client
from registry.enums.service import (HttpMethodEnum, OGCOperationEnum,
                                    OGCServiceVersionEnum)
from registry.exceptions.service import (LayerNotQueryable,
                                         OperationNotSupported)
from registry.managers.security import WebMapServiceSecurityManager
from registry.managers.service import (CatalougeServiceCapabilitiesManager,
                                       CswOperationUrlQueryableQuerySet,
                                       FeatureTypeElementXmlManager,
                                       LayerManager,
                                       WebFeatureServiceCapabilitiesManager,
                                       WebMapServiceCapabilitiesManager)
from registry.models.document import CapabilitiesDocumentModelMixin
from registry.models.metadata import (FeatureTypeMetadata, LayerMetadata,
                                      MimeType, ServiceMetadata, Style)
from registry.xmlmapper.ogc.wfs_describe_feature_type import \
    DescribedFeatureType as XmlDescribedFeatureType
from requests import Session
from requests.models import Request, Response
from simple_history.models import HistoricalRecords


class CommonServiceInfo(models.Model):
    hits = models.PositiveIntegerField(
        default=0,
        editable=False,
        verbose_name=_("hits"),
        help_text=_("how many times this metadata was requested by a client"),
    )
    is_active = models.BooleanField(
        default=False,
        verbose_name=_("is active?"),
        help_text=_(
            "Used to activate/deactivate the service. If it is deactivated, you "
            "cant request the service through the Mr. Map proxy."
        ),
    )

    class Meta:
        abstract = True


class OgcService(CapabilitiesDocumentModelMixin, ServiceMetadata, CommonServiceInfo):
    """Abstract Service model to store OGC service."""

    version: str = models.CharField(
        max_length=10,
        choices=OGCServiceVersionEnum.as_choices(),
        editable=False,
        verbose_name=_("version"),
        help_text=_("the version of the service type as sem version"),
    )
    service_url: str = models.URLField(
        max_length=4096,
        editable=False,
        verbose_name=_("url"),
        help_text=_("the base url of the service"),
    )

    objects = DefaultHistoryManager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        adding = self._state.adding
        old = None
        if not adding:
            if isinstance(self, WebMapService):
                old = WebMapService.objects.filter(pk=self.pk).first()
            elif isinstance(self, WebFeatureService):
                old = WebFeatureService.objects.filter(pk=self.pk).first()
        super().save(*args, **kwargs)
        if not adding and old and old.is_active != self.is_active:
            # the active sate of this and all descendant elements shall be changed to the new value. Bulk update
            # is the most efficient way to do it.
            if isinstance(self, WebMapService):
                self.layers.update(is_active=self.is_active)
            elif isinstance(self, WebFeatureService):
                self.featuretypes.update(is_active=self.is_active)

    def major_version(self) -> int:
        return int(self.version.split(".")[0])

    def minor_version(self) -> int:
        return int(self.version.split(".")[1])

    def fix_version(self) -> int:
        return int(self.version.split(".")[2])

    def get_session_for_request(self) -> Session:
        session = Session()
        session.proxies = PROXIES
        if hasattr(self, "auth"):
            session.auth = self.auth.get_auth_for_request()
        return session

    def send_get_request(self, url: str, timeout: int = 10) -> Response:
        return self.get_session_for_request().send(request=Request(method="GET", url=url).prepare(), timeout=timeout)

    @property
    def get_capabilities_url(self) -> str:
        """ Returns the url for the GetCapabilities operation, to use with http get method. """
        url: str = self.operation_urls.values('url').get(
            operation=OGCOperationEnum.GET_CAPABILITIES.value,
            method="Get"
        )['url']
        # TODO: handle different versions here... version 1.0.0 has other query parameters
        query_params = {
            "VERSION": self.version,
            "SERVICE": "WMS",
            "REQUEST": "GetCapabilities"}
        return update_url_query_params(url=url, params=query_params)


class WebMapService(HistoricalRecordMixin, OgcService):
    change_log = HistoricalRecords(related_name="change_logs")
    capabilities = WebMapServiceCapabilitiesManager()
    security = WebMapServiceSecurityManager()

    class Meta:
        verbose_name = _("web map service")
        verbose_name_plural = _("web map services")

    @cached_property
    def root_layer(self):
        return self.layers.get(parent=None)


class WebFeatureService(HistoricalRecordMixin, OgcService):
    change_log = HistoricalRecords(related_name="change_logs")
    capabilities = WebFeatureServiceCapabilitiesManager()
    # TODO: security = WebFeatureServiceSecurityManager()

    class Meta:
        verbose_name = _("web feature service")
        verbose_name_plural = _("web feature services")


class CatalougeService(HistoricalRecordMixin, OgcService):
    change_log = HistoricalRecords(related_name="change_logs")
    capabilities = CatalougeServiceCapabilitiesManager()
    objects = DefaultHistoryManager()

    class Meta:
        verbose_name = _("catalouge service")
        verbose_name_plural = _("catalouge services")

    def get_records_hits_url(
        self,
        type_names: str = "gmd:MD_Metadata",
        result_type: str = "hits",
        output_schema: str = "http://www.isotc211.org/2005/gmd",
        element_set_name: str = "full",
        xml_constraint: str = None
    ):
        url: str = self.operation_urls.values('url').get(
            operation=OGCOperationEnum.GET_RECORDS.value,
            method="Get"
        )['url']
        query_params = {
            "VERSION": self.version,
            "SERVICE": "CSW",
            "REQUEST": "GetRecords",
            "typeNames": type_names,
            "resultType": result_type,
            "outputSchema": output_schema,
            "elementSetName": element_set_name, }

        if xml_constraint:
            query_params.update({
                "constraintLanguage": "FILTER",
                "CONSTRAINT_LANGUAGE_VERSION": "1.1.0",
                "Constraint": xml_constraint
            })

        return update_url_query_params(url=url, params=query_params)

    def get_records_url(
        self,
        type_names: str = "gmd:MD_Metadata",
        result_type: str = "results",
        output_schema: str = "http://www.isotc211.org/2005/gmd",
        element_set_name: str = "full",
        max_records: int = 10,
        start_position: int = 1,
        xml_constraint: str = None
    ):
        url: str = self.operation_urls.values('url').get(
            operation=OGCOperationEnum.GET_RECORDS.value,
            method="Get"
        )['url']
        query_params = {
            "VERSION": self.version,
            "SERVICE": "CSW",
            "REQUEST": "GetRecords",
            "typeNames": type_names,
            "resultType": result_type,
            "outputSchema": output_schema,
            "elementSetName": element_set_name,
            "maxRecords": max_records,
            "startPosition": start_position}
        if xml_constraint:
            query_params.update({
                "constraintLanguage": "FILTER",
                "CONSTRAINT_LANGUAGE_VERSION": "1.1.0",
                "Constraint": xml_constraint
            })

        return update_url_query_params(url=url, params=query_params)

    def get_record_by_id_url(
        self,
        id: str,
        output_schema: str = "http://www.isotc211.org/2005/gmd",
        element_set_name: str = "full",
    ):
        url: str = self.operation_urls.values('url').get(
            operation=OGCOperationEnum.GET_RECORDS.value,
            method="Get"
        )['url']
        query_params = {
            "VERSION": self.version,
            "SERVICE": "CSW",
            "REQUEST": "GetRecordById",
            "outputSchema": output_schema,
            "elementSetName": element_set_name,
            "id": id,
        }
        return update_url_query_params(url=url, params=query_params)


class OperationUrl(models.Model):
    """Concrete model class to store operation urls for registered services

    With that urls we can perform all needed request to a given service.
    """

    method: str = models.CharField(
        max_length=10,
        choices=HttpMethodEnum.as_choices(),
        verbose_name=_("http method"),
        help_text=_("the http method you can perform for this url"),
    )
    # 2048 is the technically specified max length of an url. Some services urls scratches this limit.
    url: str = models.URLField(
        max_length=4096,
        editable=False,
        verbose_name=_("url"),
        help_text=_("the url for this operation"),
    )
    operation: str = models.CharField(
        max_length=30,
        choices=OGCOperationEnum.as_choices(),
        editable=False,
        verbose_name=_("operation"),
        help_text=_("the operation you can perform with this url."),
    )
    mime_types = models.ManyToManyField(
        to="MimeType",  # use string to avoid from circular import error
        blank=True,
        editable=False,
        related_name="%(class)s_operation_urls",
        related_query_name="%(class)s_operation_url",
        verbose_name=_("internet mime type"),
        help_text=_("all available mime types of the remote url"),
    )
    objects = models.Manager()

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.operation} | {self.url} ({self.method})"

    def get_url(self, request):
        url_parsed = urlparse(self.url)
        new_query = {}
        for key, value in parse_qs(url_parsed.query).items():
            new_query.update({key.upper(): value})
        url_parsed._replace(query=new_query)
        return url_parsed.geturl()
        # TODO: check if service is secured and if so return the secured url
        parsed_request_url = urlparse(request.get_full_path())
        parsed_url = urlparse(self.url)
        parsed_url._replace(netloc=parsed_request_url.netloc)
        return parsed_url.geturl()


class WebMapServiceOperationUrl(OperationUrl):
    service = models.ForeignKey(
        to=WebMapService,
        on_delete=models.CASCADE,
        editable=False,
        related_name="operation_urls",
        related_query_name="operation_url",
        verbose_name=_("related web map service"),
        help_text=_("the web map service for that this url can be used for."),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["method", "operation", "service"],
                name="%(app_label)s_%(class)s_unique_together_method_id_operation_service",
            )
        ]


class WebFeatureServiceOperationUrl(OperationUrl):
    service = models.ForeignKey(
        to=WebFeatureService,
        on_delete=models.CASCADE,
        editable=False,
        related_name="operation_urls",
        related_query_name="operation_url",
        verbose_name=_("related web feature service"),
        help_text=_(
            "the web feature service for that this url can be used for."),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["method", "operation", "service"],
                name="%(app_label)s_%(class)s_unique_together_method_id_operation_service",
            )
        ]


class CatalougeServiceOperationUrl(OperationUrl):
    service = models.ForeignKey(
        to=CatalougeService,
        on_delete=models.CASCADE,
        editable=False,
        related_name="operation_urls",
        related_query_name="operation_url",
        verbose_name=_("related catalouge service"),
        help_text=_("the catalouge service for that this url can be used for."),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["method", "operation", "service"],
                name="%(app_label)s_%(class)s_unique_together_method_id_operation_service",
            )
        ]


class CswOperationUrlQueryable(models.Model):
    # TODO: remove this model and merge it with CatalougeServiceOperationUrl
    #  CatalougeServiceOperationUrl can have constraints.
    #  For harvesting processing we need the concrete constraint value for type with correct namespace.
    #  Like dc:type or apiso:Type to build the GetRecord request correctly

    operation_url = models.ForeignKey(
        to=CatalougeServiceOperationUrl,
        on_delete=models.CASCADE,
        related_name="queryables",
        related_query_name="queryable"
    )
    value = models.CharField(
        max_length=64
    )

    objects: models.Manager = CswOperationUrlQueryableQuerySet.as_manager()

    def __str__(self) -> str:
        return self.value


class ServiceElement(CapabilitiesDocumentModelMixin, CommonServiceInfo):
    """Abstract model class to generalize some fields and functions for layers and feature types"""

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    identifier = models.CharField(
        max_length=500,
        null=True,
        editable=False,
        verbose_name=_("identifier"),
        help_text=_(
            "this is a string which identifies the element on the remote service."
        ),
    )
    bbox_lat_lon = gis_models.PolygonField(
        null=True,  # to support inherited bbox from ancestor layer null=True
        blank=True,
        editable=False,
        verbose_name=_("bounding box"),
        help_text=_(
            "bounding box shall be supplied regardless of what CRS the map "
            "server may support, but it may be approximate if the data are "
            "not natively in geographic coordinates. The purpose of bounding"
            " box is to facilitate geographic searches without requiring "
            "coordinate transformations by the search engine."
        ),
    )
    reference_systems = models.ManyToManyField(
        to="ReferenceSystem",  # to avoid circular import error
        related_name="%(class)s",
        related_query_name="%(class)s",
        blank=True,
        editable=False,
        verbose_name=_("reference systems"),
        help_text=_("all reference systems which this element supports"),
    )
    # todo:
    xml_mapper_cls = None

    class Meta:
        abstract = True

    def __str__(self):
        try:
            return f"{self.metadata.title} ({self.pk})"
        except Exception:
            return str(self.pk)

    def get_dataset_table_url(self) -> str:
        if self.dataset_metadata.exists():
            try:
                return (
                    reverse(f"{self._meta.app_label}:dataset_metadata_list")
                    + f'?id__in={",".join([str(dataset.pk) for dataset in self.dataset_metadata.all()])}'
                )
            except NoReverseMatch:
                pass
        return ""


class Layer(HistoricalRecordMixin, LayerMetadata, ServiceElement, MPTTModel):
    """Concrete model class to store parsed layers.

    :attr objects: custom models manager :class:`registry.managers.service.LayerManager`
    """

    service: WebMapService = models.ForeignKey(
        to=WebMapService,
        on_delete=models.CASCADE,
        editable=False,
        related_name="layers",
        related_query_name="layer",
        verbose_name=_("service"),
        help_text=_("the extras service where this element is part of"),
    )
    parent = TreeForeignKey(
        to="self",
        on_delete=models.CASCADE,
        null=True,
        editable=False,
        related_name="children",
        related_query_name="child",
        verbose_name=_("parent layer"),
        help_text=_("the ancestor of this layer."),
    )
    is_queryable: bool = models.BooleanField(
        default=False,
        editable=False,
        verbose_name=_("is queryable"),
        help_text=_(
            "flag to signal if this layer provides factual information or not."
            " Parsed from capabilities."
        ),
    )
    is_opaque: bool = models.BooleanField(
        default=False,
        editable=False,
        verbose_name=_("is opaque"),
        help_text=_(
            "flag to signal if this layer support transparency content or not. "
            "Parsed from capabilities."
        ),
    )
    is_cascaded: bool = models.BooleanField(
        default=False,
        editable=False,
        verbose_name=_("is cascaded"),
        help_text=_(
            "WMS cascading allows to expose layers coming from other WMS servers "
            "as if they were local layers"
        ),
    )
    scale_min: float = models.FloatField(
        null=True,
        blank=True,
        editable=False,
        verbose_name=_("scale minimum value"),
        help_text=_(
            "minimum scale for a possible request to this layer. If the request is "
            "out of the given scope, the service will response with empty transparent"
            "images. None value means no restriction."
        ),
    )
    scale_max: float = models.FloatField(
        null=True,
        blank=True,
        editable=False,
        verbose_name=_("scale maximum value"),
        help_text=_(
            "maximum scale for a possible request to this layer. If the request is "
            "out of the given scope, the service will response with empty transparent"
            "images. None value means no restriction."
        ),
    )
    change_log = HistoricalRecords(
        related_name="change_logs", excluded_fields=["lft", "rght", "tree_id", "level"]
    )

    objects = LayerManager()

    class Meta:
        verbose_name = _("layer")
        verbose_name_plural = _("layers")

    def save(self, *args, **kwargs):
        """Custom save function to handle activate process for the layer, all his descendants and his related service.
        If the given layer shall be active, the complete family (:meth:`mptt.models.MPTTModel.get_family`) of this
        layer and the related :class:`registry.models.service.Service` will be updated with ``ìs_active=True``.
        If the given layer shall be inactive, all descendants (:meth:`mptt.models.MPTTModel.get_descendants`) of this
        layer will be updated with ``is_active=False``.
        """
        adding = self._state.adding
        old = None
        if not adding:
            old = Layer.objects.filter(pk=self.pk).first()
        super().save(*args, **kwargs)
        if not adding and old and old.is_active != self.is_active:
            # the active sate of this and all descendant layers shall be changed to the new value. Bulk update
            # is the most efficient way to do it.
            if self.is_active:
                self.get_family().update(is_active=self.is_active)
                WebMapService.objects.filter(pk=self.service_id).update(
                    is_active=self.is_active
                )
            else:
                self.get_descendants().update(is_active=self.is_active)

    def get_value_from_ancestor(self, attr_name: str) -> tuple:
        """Return a tuple of a boolean, if this layers has prefetched ancestors and as second value of the tuple the first founded value or None"""
        if hasattr(self, 'ancestors'):
            return True, next((getattr(ancestor, attr_name) for ancestor in self.ancestors if getattr(ancestor, attr_name) is not None), None)
        else:
            return False, None

    @cached_property
    def get_scale_min(self) -> float:
        """Return the scale min value of this layer based on the inheritance from other layers as requested in the ogc specs.

        .. note:: excerpt from ogc specs

           * **ogc wms 1.1.1**: ScaleHint is inherited by child Layers.  A ScaleHint declaration in the child replaces the
             any declaration inherited from the parent. (see section 7.1.4.5.8 ScaleHint)


        :return: self.scale_min if not None else scale_min from the first ancestors where scale_min is not None
        :rtype: :class:`django.contrib.gis.geos.polygon`
        """
        if self.scale_min:
            return self.scale_min
        else:
            has_prefetched_ancestors, inherited_scale_min = self.get_value_from_ancestor(
                'scale_min')
            return inherited_scale_min if has_prefetched_ancestors else (
                self.get_ancestors()
                .exclude(scale_min=None)
                .values_list("scale_min", flat=True)
                .first()
            )

    @cached_property
    def get_scale_max(self) -> float:
        """Return the scale min value of this layer based on the inheritance from other layers as requested in the ogc specs.

        .. note:: excerpt from ogc specs

           * **ogc wms 1.1.1**: ScaleHint is inherited by child Layers.  A ScaleHint declaration in the child replaces the
             any declaration inherited from the parent. (see section 7.1.4.5.8 ScaleHint)


        :return: self.scale_max if not None else scale_max from the first ancestors where scale_max is not None
        :rtype: :class:`django.contrib.gis.geos.polygon`
        """
        if self.scale_max:
            return self.scale_max
        else:
            has_prefetched_ancestors, inherited_scale_max = self.get_value_from_ancestor(
                'scale_max')
            return inherited_scale_max if has_prefetched_ancestors else (
                self.get_ancestors()
                .exclude(scale_max=None)
                .values_list("scale_max", flat=True)
                .first()
            )

    @cached_property
    def get_bbox(self) -> Polygon:
        """Return the bbox of this layer based on the inheritance from other layers as requested in the ogc specs.

        .. note:: excerpt from ogc specs

           * **ogc wms 1.1.1**: Every Layer shall have exactly one <LatLonBoundingBox> element that is either stated
             explicitly or inherited from a parent Layer. (see section 7.1.4.5.6)
           * **ogc wms 1.3.0**: Every named Layer shall have exactly one <EX_GeographicBoundingBox> element that is
             either stated explicitly or inherited from a parent Layer. (see section 7.2.4.6.6)


        :return: self.bbox_lat_lon if not None else bbox_lat_lon from the first ancestors where bbox_lat_lon is not None
        :rtype: :class:`django.contrib.gis.geos.polygon`
        """
        if self.bbox_lat_lon:
            return self.bbox_lat_lon
        else:
            has_prefetched_ancestors, inherited_bbox = self.get_value_from_ancestor(
                'bbox_lat_lon')
            return inherited_bbox if has_prefetched_ancestors else (
                self.get_ancestors()
                .exclude(bbox_lat_lon=None)
                .values_list("bbox_lat_lon", flat=True)
                .first()
            )

    @cached_property
    def get_reference_systems(self) -> QuerySet:
        """Return all supported reference systems for this layer, based on the inheritance from other layers as
        requested in the ogc specs.

        .. note:: excerpt from ogc specs

           * **ogc wms 1.1.1**: Every Layer shall have at least one <SRS> element that is either stated explicitly or
             inherited from a parent Layer (see section 7.1.4.5.5).
           * **ogc wms 1.3.0**: Every Layer is available in one or more layer coordinate reference systems. 6.7.3
             discusses the Layer CRS. In order to indicate which Layer CRSs are available, every named Layer shall have
             at least one <CRS> element that is either stated explicitly or inherited from a parent Layer.

        :return: all supported reference systems :class:`registry.models.metadata.ReferenceSystem` for this layer
        :rtype: :class:`django.db.models.query.QuerySet`
        """
        if self.reference_systems.exists():
            return self.reference_systems.all()
        from registry.models import \
            ReferenceSystem  # to avoid circular import errors

        return ReferenceSystem.objects.filter(layer__in=self.get_ancestors()).distinct(
            "code", "prefix"
        )

    @cached_property
    def get_dimensions(self) -> QuerySet:
        """Return all dimensions of this layer, based on the inheritance from other layers as requested in the ogc
        specs.

        .. note:: excerpt from ogc specs

           * **ogc wms 1.1.1**: Dimension declarations are inherited from parent Layers. Any new Dimension declarations
             in the child are added to the list inherited from the parent. A child **shall not** redefine a  Dimension
             with the same name attribute as one that was inherited. Extent declarations are inherited from parent
             Layers. Any Extent declarations in the child with the same name attribute as one inherited from the parent
             replaces the value declared by the parent.  A Layer shall not declare an Extent unless a Dimension with the
             same name has been declared or inherited earlier in the Capabilities XML.

           * **ogc wms 1.3.0**: Dimension  declarations  are  inherited  from  parent  Layers.  Any  new  Dimension
             declaration  in  the  child  with  the  same name attribute as one inherited from the parent replaces the
             value declared by the parent.


        :return: all dimensions of this layer
        :rtype: :class:`django.db.models.query.QuerySet`
        """
        if self.layer_dimensions.exists():
            return self.layer_dimensions.all()
        from registry.models import \
            Dimension  # to avoid circular import errors

        return Dimension.objects.filter(
            layer__in=self.get_ancestors(ascending=True)
        ).distinct("name")

    def get_map_url(self, bbox: Polygon = None, format: str = None, style: Style = None, width: int = 1, height: int = 1, transparent: bool = False, bgcolor="=0xFFFFFF", exceptions="XML") -> str:
        """ Returns the url for the GetMap operation, to use with http get method to request this specific layer. """
        if not format:

            operation_url: dict = self.service.operation_urls.values('id', 'url').get(
                operation=OGCOperationEnum.GET_MAP.value,
                method="Get"
            )
            url: str = operation_url["url"]
            image_format = MimeType.objects.filter(
                webmapserviceoperationurl_operation_url__pk=operation_url['id'],
                mime_type__istartswith="image/").exclude(mime_type__icontains="svg").values('mime_type').first()['mime_type']
        else:
            if hasattr(self.service, "prefetched_get_map_operation_url"):
                url: str = self.service.prefetched_get_map_operation_url[0].url
            else:
                url: str = self.service.operation_urls.values('url').get(
                    operation=OGCOperationEnum.GET_MAP.value,
                    method="Get"
                )["url"]
                # TODO: check if this format is supported by the layer...
            image_format: str = format
        _bbox: Polygon = bbox if bbox else self.get_bbox

        # if self.get_scale_max:
        #     # 1/100000
        #     upper_left = Point(_bbox.extend[0], _bbox.extend[1])
        #     lower_right = Point(_bbox.extend[2], _bbox.extend[3])
        #     distance = upper_left.distance(lower_right)
        #     scale_bbox = distance / \
        #         math.sqrt(pow(width, 2) + pow(height, 2)) / 0.00028
        #     if scale_bbox > self.get_scale_max:
        #         # TODO: scale the bbox
        #         pass

        # TODO: handle different versions here... version 1.0.0 has other query parameters
        query_params = {
            "VERSION": self.service.version,
            "REQUEST": "GetMap",
            "SERVICE": "WMS",
            "LAYERS": self.identifier,
            "STYLES": style.name if style else "",
            "CRS" if self.service.minor_version == 3 else "SRS": f"EPSG:{_bbox.crs.srid}",
            "BBOX": ",".join(map(str, _bbox.extent)),
            "WIDTH": width,
            "HEIGHT": height,
            "FORMAT": image_format,
        }
        if transparent:
            query_params.update({"TRANSPARENT": "True"})

        return update_url_query_params(url=url, params=query_params)

    def get_feature_info_url(self, column: int = None, row: int = None, info_format: str = None, *args, **kwargs):
        if not self.is_queryable:
            raise LayerNotQueryable(
                f"Layer '{self.identifier}' is not queryable.")
        try:
            if not info_format:
                url_and_id: dict = self.service.operation_urls.values('id', 'url').get(
                    operation=OGCOperationEnum.GET_FEATURE_INFO.value,
                    method="Get"
                )
                url: str = url_and_id["url"]
                _info_format: str = MimeType.objects.filter(
                    webmapserviceoperationurl_operation_url__pk=url_and_id['id'], mime_type__istartswith="text/").values('mime_type').first()['mime_type']
            else:
                url: str = self.service.operation_urls.values('url').get(
                    operation=OGCOperationEnum.GET_FEATURE_INFO.value,
                    method="Get"
                )["url"]
                # TODO: check if this format is supported by the layer...
                _info_format: str = "text/plain"
        except WebMapServiceOperationUrl.DoesNotExist:
            raise OperationNotSupported(
                f"Service {self.service.title} does not suppoert operation GetFeatureInfo")

        query_params = {
            "VERSION": self.service.version,
            "REQUEST": "GetFeatureInfo",
            "QUERY_LAYERS": self.identifier,
            "INFO_FORMAT": _info_format,
            "I" if self.service.minor_version == 3 else "X": column if column else kwargs.get('width', 1),
            "J" if self.service.minor_version == 3 else "Y": row if row else kwargs.get('row', 1)

        }
        url = update_url_base(url=self.get_map_url(*args, **kwargs), base=url)
        return update_url_query_params(url=url, params=query_params)


class FeatureType(HistoricalRecordMixin, FeatureTypeMetadata, ServiceElement):
    """Concrete model class to store parsed FeatureType.

    :attr objects: custom models manager :class:`registry.managers.service.FeatureTypeManager`
    """

    service: WebFeatureService = models.ForeignKey(
        to=WebFeatureService,
        on_delete=models.CASCADE,
        editable=False,
        related_name="featuretypes",
        related_query_name="featuretype",
        verbose_name=_("service"),
        help_text=_("the extras service where this element is part of"),
    )
    output_formats = models.ManyToManyField(
        to="MimeType",  # use string to avoid from circular import error
        blank=True,
        editable=False,
        related_name="feature_types",
        related_query_name="feature_type",
        verbose_name=_("output formats"),
        help_text=_(
            "This is a list of MIME types indicating the output formats "
            "that may be generated for a feature type.  If this optional "
            "element is not specified, then all the result formats "
            "listed for the GetFeature operation are assumed to be "
            "supported. "
        ),
    )
    describe_feature_type_document = models.TextField(
        null=True,
        verbose_name=_("describe feature type"),
        help_text=_(
            "the fetched content of the download describe feature" " type document."
        ),
    )
    change_log = HistoricalRecords(related_name="change_logs")
    objects = DefaultHistoryManager()

    class Meta:
        verbose_name = _("feature type")
        verbose_name_plural = _("feature types")

    def save(self, *args, **kwargs):
        """Custom save function to handle activate process for the feature type and his related service.
        If the given feature type shall be active, the feature type it self and the related
        :class:`registry.models.service.Service` will be updated with ``is_active=True``.
        If the given feature type shall be inactive only the feature type it self will be updated with
        ``is_active=False``.
        """
        adding = self._state.adding
        super().save(*args, **kwargs)
        if not adding and self.is_active:
            WebFeatureService.objects.filter(pk=self.service_id).update(
                is_active=self.is_active
            )

    def fetch_describe_feature_type_document(self, save=True):
        """Return the fetched described feature type document and update the content if save is True"""

        client = get_client(capabilities=self.service.xml_backup,
                            session=self.service.get_session_for_request())
        response = client.send_request(
            client.prepare_describe_feature_type_request(type_names=self.identifier))
        if response.status_code <= 202 and "xml" in response.headers["content-type"]:
            self.describe_feature_type_document = response.content
            if save:
                self.save()
            return self.describe_feature_type_document
        else:
            settings.ROOT_LOGGER.error(
                msg=f"can't fetch describe feature type document. response status code: {response.status_code}; response body: {response.content}"
            )

    def parse(self):
        """Return the parsed self.remote_content

        Raises:
            ValueError: if self.remote_content is null
        """
        if self.describe_feature_type_document:
            parsed_feature_type_elements = xmlmap.load_xmlobject_from_string(
                string=self.describe_feature_type_document,
                xmlclass=XmlDescribedFeatureType,
            )
            return parsed_feature_type_elements
        else:
            raise ValueError(
                "there is no fetched content. You need to call fetch_describe_feature_type_document() "
                "first."
            )

    def create_element_instances(self):
        """Return the created FeatureTypeElement record(s)"""
        return FeatureTypeProperty.xml_objects.create_from_parsed_xml(
            parsed_xml=self.parse(), related_object=self
        )


class FeatureTypeProperty(models.Model):
    max_occurs = models.IntegerField(default=1)
    min_occurs = models.IntegerField(default=0)
    name = models.CharField(max_length=255)
    data_type = models.CharField(max_length=255, null=True, blank=True)
    required = models.BooleanField(default=False)
    feature_type = models.ForeignKey(
        to=FeatureType,
        # editable=False,
        related_name="properties",
        related_query_name="property",
        on_delete=models.CASCADE,
        verbose_name=_("feature type"),
        help_text=_("related feature type of this property"),
    )
    objects = models.Manager()
    xml_objects = FeatureTypeElementXmlManager()

    class Meta:
        verbose_name = _("feature type property")
        verbose_name_plural = _("feature type properties")
        ordering = ["-name"]

    def __str__(self):
        return self.name
