from logging import Logger
from uuid import uuid4

from django.conf import settings
from django.contrib.gis.db import models
from django.contrib.gis.db import models as gis_models
from django.contrib.gis.geos import Polygon
from django.contrib.postgres.indexes import GistIndex
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.urls import NoReverseMatch, reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from extras.decorators import warn_on_queries
from extras.managers import DefaultHistoryManager
from extras.models import (AdditionalTimeFieldsHistoricalModel,
                           HistoricalRecordMixin)
from extras.utils import update_url_base, update_url_query_params
from lxml import etree
from mptt2.models import Node
from registry.enums.service import (HttpMethodEnum, OGCOperationEnum,
                                    OGCServiceVersionEnum)
from registry.exceptions.service import (LayerNotQueryable,
                                         OperationNotSupported)
from registry.managers.security import (WebFeatureServiceSecurityManager,
                                        WebMapServiceSecurityManager)
from registry.managers.service import (CatalogueServiceManager, LayerManager,
                                       WebFeatureServiceQuerySet,
                                       WebMapServiceQuerySet)
from registry.mappers.configs import XPATH_MAP
from registry.mappers.persistence.handler import PersistenceHandler
from registry.mappers.xml_mapper import XmlMapper
from registry.models.document import CapabilitiesDocumentModelMixin
from registry.models.metadata import (AbstractMetadata, FeatureTypeMetadata,
                                      LayerMetadata, MimeType, ServiceMetadata,
                                      Style)
from registry.ows_lib.client.core import OgcClient
from registry.ows_lib.csw.csw import CatalogueServiceClient
from registry.ows_lib.wfs.wfs import WebFeatureServiceClient
from registry.ows_lib.wms.wms import WebMapServiceClient
from requests import Request, Response, Session
from simple_history.models import HistoricalRecords

logger: Logger = settings.ROOT_LOGGER


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

    version = models.PositiveSmallIntegerField(
        choices=OGCServiceVersionEnum.choices,
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
    update_candidate = models.OneToOneField(
        to="self",
        on_delete=models.CASCADE,
        related_name="is_update_candidate_of",
        related_query_name="is_update_candidate_of",
        null=True,
        blank=True,
        editable=False,
        verbose_name=_("update candidate"),
        help_text=_("this is the update candidate of this service.")
    )

    objects = DefaultHistoryManager()

    class Meta:
        abstract = True

        indexes = [
            models.Index(fields=["update_candidate",]),
        ]

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
        return int(OGCServiceVersionEnum(self.version).label.split(".")[0])

    def minor_version(self) -> int:
        return int(OGCServiceVersionEnum(self.version).label.split(".")[1])

    def fix_version(self) -> int:
        return int(OGCServiceVersionEnum(self.version).label.split(".")[2])

    def get_session_for_request(self) -> Session:
        session = Session()
        # session.proxies.update(PROXIES)
        try:
            session.auth = self.auth.get_auth_for_request()
        except ObjectDoesNotExist:
            # No service authentication existing...
            pass

        return session

    def get_service_type(self):
        match(self.__class__.__name__):
            case "WebMapService":
                return "WMS"
            case "WebFeatureService":
                return "WFS"
            case "CatalogueService":
                return "CSW"
            case _:
                return None

    @property
    def get_capabilities_url(self) -> str | bytes:
        cap_url = self.operation_urls.filter(
            method=HttpMethodEnum.GET.value,
            operation=OGCOperationEnum.GET_CAPABILITIES.value,
        ).values_list("url", flat=True).first()

        cap_url = update_url_query_params(
            cap_url,
            {
                "SERVICE": self.get_service_type(),
                "VERSION": OGCServiceVersionEnum(self.version).label,
                "REQUEST": "GetCapabilities",
            }
        )

    @property
    def remote_capabilities(self) -> bytes | None:
        request = Request(method="GET", url=self.get_capabilities_url)
        session = self.get_session_for_request()
        response = session.send(request=request.prepare())
        if response.status_code <= 202 and "xml" in response.headers["content-type"]:
            return response.content

    @property
    def capabilities(self) -> str | bytes:
        try:
            cap = self.xml_backup
        except FileNotFoundError:
            # Corrupted service.. no capability file stored in file system. We fallback by trying the GetCapabilities url.

            cap = self.get_capabilities_url

            logger.warning(
                msg=f"{self} has no capabilities file stored. Trying fallback by url.",
                extra={
                    "structured_data": {
                        "metaSDIS@django": {
                            "capabilities_url": cap
                        }
                    }
                })
        finally:
            return cap

    @property
    def client(self) -> OgcClient:
        raise NotImplementedError

    def metadata_equal(self, other: "OgcService") -> bool:
        if not isinstance(other, OgcService):
            raise NotImplementedError

        return (
            self.title == other.title and
            self.abstract == other.abstract

        )


class WebMapService(HistoricalRecordMixin, OgcService):
    change_log = HistoricalRecords(
        related_name="change_logs",
        excluded_fields="search_vector",
        bases=[AdditionalTimeFieldsHistoricalModel,],
    )

    objects = WebMapServiceQuerySet.as_manager()
    security = WebMapServiceSecurityManager()
    history = DefaultHistoryManager()

    class Meta:
        verbose_name = _("web map service")
        verbose_name_plural = _("web map services")
        indexes = [
        ] + OgcService.Meta.indexes + AbstractMetadata.Meta.indexes

    @cached_property
    def root_layer(self):
        """
        Use prefetched layers if available to avoid an extra DB hit
        and to preserve annotations. Fall back to a DB query otherwise.
        """
        if (
            hasattr(self, "_prefetched_objects_cache")
            and "layers" in self._prefetched_objects_cache
        ):
            for layer in self._prefetched_objects_cache["layers"]:
                if layer.mptt_parent_id is None:
                    return layer

        # Not prefetched → let the DB do the work
        return self.layers.get(mptt_parent=None)

    @property
    def client(self) -> WebMapServiceClient:
        return WebMapServiceClient(
            capabilities=self.capabilities,
            session=self.get_session_for_request()
        )

    @warn_on_queries
    def xml_secured(self, request) -> str:
        new_url = self.get_secured_url(
            request=request, url_name="wms-operation")

        # Hint: this can only work performant if all related objects are retreived with select_related and prefetch_related
        # therefore we have the @warn_on_queries decorator here to warn us if this is not the case.
        # We simply iterate over all related objects and update the urls.
        for operation_url in self.operation_urls.all():
            operation_url.url = new_url
        if self.service_url:
            self.service_url = new_url
        for layer in self.layers.all():
            for style in layer.styles.all():
                style.legend_url.legend_url.url = f"{new_url}{style.legend_url.legend_url.url.split('?', 1)[-1]}"

        # TODO: only support xml Exception format --> remove all others
        # TODO: camouflage metadata urls also

        capabilities_xml = self.get_updated_capabilitites()

        return etree.tostring(
            capabilities_xml.getroottree().getroot(),
            pretty_print=True,
            xml_declaration=True,
            encoding="UTF-8"
        )

    def get_updated_capabilitites(self) -> etree.ElementTree:
        """
        FIXME: check if self is well prefetched.
        If not call self.objects.prefetch_whole_service(
            ...    with_sibling_index=True,
            ...    prefetch_spec={
            ...         "prefetch": {
            ...             "layers": {
            ...                 "select": ["mptt_parent"],
            ...             }
            ...         }
            ...     }
            ...  )
        Otherwise this will fail caulse layer index calculation for xpath compiling will fail

        """
        return super().get_updated_capabilitites()


class WebFeatureService(HistoricalRecordMixin, OgcService):
    change_log = HistoricalRecords(
        related_name="change_logs",
        excluded_fields="search_vector",
        bases=[AdditionalTimeFieldsHistoricalModel,],
    )

    objects = WebFeatureServiceQuerySet.as_manager()
    security = WebFeatureServiceSecurityManager()
    history = DefaultHistoryManager()

    class Meta:
        verbose_name = _("web feature service")
        verbose_name_plural = _("web feature services")
        indexes = [
        ] + OgcService.Meta.indexes + AbstractMetadata.Meta.indexes

    @property
    def client(self) -> WebFeatureServiceClient:
        return WebFeatureServiceClient(
            capabilities=self.capabilities,
            session=self.get_session_for_request()
        )


class CatalogueService(HistoricalRecordMixin, OgcService):
    # TODO: the max step size should be checked by registrating the service, harvesting the service, updating the service.
    max_step_size = models.IntegerField(
        verbose_name=_("max step size"),
        help_text=_(
            "the maximum step size this csw can handle by a single GetRecords request."),
        default=50,
    )
    change_log = HistoricalRecords(
        related_name="change_logs",
        excluded_fields="search_vector",
        bases=[AdditionalTimeFieldsHistoricalModel,],
    )
    objects = CatalogueServiceManager()
    history = DefaultHistoryManager()

    class Meta:
        verbose_name = _("catalogue service")
        verbose_name_plural = _("catalogue services")
        indexes = [
        ] + OgcService.Meta.indexes + AbstractMetadata.Meta.indexes

    @property
    def client(self) -> CatalogueServiceClient:
        return CatalogueServiceClient(
            capabilities=self.capabilities,
            session=self.get_session_for_request()
        )


class OperationUrl(models.Model):
    """Concrete model class to store operation urls for registered services

    With that urls we can perform all needed request to a given service.
    """
    method: str = models.PositiveSmallIntegerField(
        choices=HttpMethodEnum.choices,
        verbose_name=_("http method"),
        help_text=_("the http method you can perform for this url"),
    )
    operation: str = models.PositiveSmallIntegerField(
        choices=OGCOperationEnum.choices,
        # editable=False,
        verbose_name=_("operation"),
        help_text=_("the operation you can perform with this url."),
    )
    # 2048 is the technically specified max length of an url. Some services urls scratches this limit.
    url: str = models.URLField(
        max_length=4096,
        # editable=False,
        verbose_name=_("url"),
        help_text=_("the url for this operation"),
    )
    mime_types = models.ManyToManyField(
        to="MimeType",  # use string to avoid from circular import error
        blank=True,
        # editable=False,
        related_name="%(class)s_operation_urls",
        related_query_name="%(class)s_operation_url",
        verbose_name=_("internet mime type"),
        help_text=_("all available mime types of the remote url"),
    )

    objects = models.Manager()

    class Meta:
        abstract = True

    def __str__(self):
        return f"{OGCOperationEnum(self.operation).label} | {self.url} ({HttpMethodEnum(self.method).label})"

    # def get_url(self, request):
    #     url_parsed = urlparse(self.url)
    #     new_query = {}
    #     for key, value in parse_qs(url_parsed.query).items():
    #         new_query.update({key.upper(): value})
    #     url_parsed._replace(query=new_query)
    #     return url_parsed.geturl()
    #     # TODO: check if service is secured and if so return the secured url
    #     parsed_request_url = urlparse(request.get_full_path())
    #     parsed_url = urlparse(self.url)
    #     parsed_url._replace(netloc=parsed_request_url.netloc)
    #     return parsed_url.geturl()


class WebMapServiceOperationUrl(OperationUrl):
    service = models.ForeignKey(
        to=WebMapService,
        on_delete=models.CASCADE,
        # editable=False,
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


class CatalogueServiceOperationUrl(OperationUrl):
    service = models.ForeignKey(
        to=CatalogueService,
        on_delete=models.CASCADE,
        editable=False,
        related_name="operation_urls",
        related_query_name="operation_url",
        verbose_name=_("related catalogue service"),
        help_text=_("the catalogue service for that this url can be used for."),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["method", "operation", "service"],
                name="%(app_label)s_%(class)s_unique_together_method_id_operation_service",
            )
        ]


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
    time_extents = models.ManyToManyField(
        to="TimeExtent",
        blank=True,
        editable=False,
        related_name="%(class)s",
        related_query_name="%(class)s",
        verbose_name=_("time extent"),
        help_text=_("all time extents which are available for this layer."),
    )

    class Meta:
        abstract = True
        indexes = [
            GistIndex(
                fields=["bbox_lat_lon"],
                condition=Q(bbox_lat_lon__isnull=False),
                name="%(class)s_bbox_not_null",
            ),
        ]

    def __str__(self):
        try:
            return f"{self.metadata.title} ({self.pk})"
        except Exception:
            return str(self.pk)

    def get_dataset_table_url(self) -> str:
        if self.registry_datasetmetadatarecord_metadata_records.exists():
            try:
                return (
                    reverse(f"{self._meta.app_label}:dataset_metadata_list")
                    + f'?id__in={",".join([str(dataset.pk)
                                          for dataset in self.registry_datasetmetadatarecord_metadata_records.all()])}'
                )
            except NoReverseMatch:
                pass
        return ""


class Layer(HistoricalRecordMixin, LayerMetadata, ServiceElement, Node):
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
        related_name="change_logs",
        excluded_fields="search_vector",
        bases=[AdditionalTimeFieldsHistoricalModel,],
    )

    objects = LayerManager()
    history = DefaultHistoryManager()

    class Meta:
        verbose_name = _("layer")
        verbose_name_plural = _("layers")
        indexes = [
        ] + Node.Meta.indexes + AbstractMetadata.Meta.indexes + ServiceElement.Meta.indexes
        constraints = [
            models.UniqueConstraint(
                fields=["service", "identifier"],
                name="unique_identifer_per_wms",
            )
        ] + Node.Meta.constraints + AbstractMetadata.Meta.constraints
        # TODO: add a constraint, which checks if parent is None and bbox is None. This is not allowed

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

    def get_map_url(self, bbox: Polygon = None, format: str = None, style: Style = None, width: int = 1, height: int = 1, transparent: bool = False, bgcolor="=0xFFFFFF", exceptions="XML") -> str:
        """ Returns the url for the GetMap operation, to use with http get method to request this specific layer. """
        if not format:

            operation_url: dict = self.service.operation_urls.values('id', 'url').get(
                operation=OGCOperationEnum.GET_MAP.value,
                method=HttpMethodEnum.GET.value
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
                    method=HttpMethodEnum.GET.value
                )["url"]
                # TODO: check if this format is supported by the layer...
            image_format: str = format

        if bbox:
            _bbox: Polygon = bbox
        else:
            if hasattr(self, "bbox_lat_lon_inherited"):
                _bbox: Polygon = self.bbox_lat_lon_inherited
            else:
                _bbox: Polygon = Layer.objects.with_inherited_attributes_cte(
                ).values_list("bbox_lat_lon_inherited", flat=True).get(pk=self.pk)

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
            "VERSION": OGCServiceVersionEnum(self.service.version).label,
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
                    method=HttpMethodEnum.GET.value
                )
                url: str = url_and_id["url"]
                _info_format: str = MimeType.objects.filter(
                    webmapserviceoperationurl_operation_url__pk=url_and_id['id'], mime_type__istartswith="text/").values('mime_type').first()['mime_type']
            else:
                url: str = self.service.operation_urls.values('url').get(
                    operation=OGCOperationEnum.GET_FEATURE_INFO.value,
                    method=HttpMethodEnum.GET.value
                )["url"]
                # TODO: check if this format is supported by the layer...
                _info_format: str = "text/plain"
        except WebMapServiceOperationUrl.DoesNotExist:
            raise OperationNotSupported(
                f"Service {self.service.title} does not suppoert operation GetFeatureInfo")

        query_params = {
            "VERSION": OGCServiceVersionEnum(self.service.version).label,
            "REQUEST": "GetFeatureInfo",
            "QUERY_LAYERS": self.identifier,
            "INFO_FORMAT": _info_format,
            "I" if self.service.minor_version == 3 else "X": column if column else kwargs.get('width', 1),
            "J" if self.service.minor_version == 3 else "Y": row if row else kwargs.get('row', 1)

        }
        url = update_url_base(url=self.get_map_url(*args, **kwargs), base=url)
        return update_url_query_params(url=url, params=query_params)

    def same_identity(self, other: "Layer") -> bool:
        if not isinstance(other, Layer):
            raise NotImplementedError

        return self.identifier == other.identifier

    def metadata_equal(self, other: "Layer") -> bool:
        if not isinstance(other, Layer):
            raise NotImplementedError

        return (
            self.title == other.title and
            self.abstract == other.abstract and
            self.is_queryable == other.is_queryable and
            self.is_opaque == other.is_opaque and
            self.scale_min == other.scale_min and
            self.scale_max == other.scale_max
        )

    def structure_equal(self, other: "Layer") -> bool:
        if not isinstance(other, Layer):
            raise NotImplementedError

        return (
            self.mptt_lft == other.mptt_lft and
            self.mptt_rgt == other.mptt_rgt and
            self.mptt_depth == other.mptt_depth
        )

    def equals_remote_layer(self, other: "Layer") -> bool:
        if not isinstance(other, Layer):
            raise NotImplementedError

        if not self.same_identity(other):
            return False

        if not self.metadata_equal(other):
            return False

        if not self.structure_equal(other):
            return False

        return True


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
    # TODO: this srs needs to be added to reference_systems per annotation or otherwise for search purpose
    default_reference_system = models.ForeignKey(
        to="ReferenceSystem",  # to avoid circular import error
        on_delete=models.PROTECT,
        related_name="as_default_featuretype",
        related_query_name="as_default_featuretypes",
        verbose_name=_("default reference system"),
        help_text=_("the default reference system for this feature type"),
    )

    change_log = HistoricalRecords(
        related_name="change_logs",
        excluded_fields="search_vector",
        bases=[AdditionalTimeFieldsHistoricalModel,],
    )
    objects = DefaultHistoryManager()
    history = DefaultHistoryManager()

    class Meta:
        verbose_name = _("feature type")
        verbose_name_plural = _("feature types")
        indexes = [
        ] + AbstractMetadata.Meta.indexes + ServiceElement.Meta.indexes
        constraints = [
            models.UniqueConstraint(
                fields=["service", "identifier"],
                name="unique_identifer_per_wfs",
            )
        ] + AbstractMetadata.Meta.constraints

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
        response = self.service.client.send_request(
            request=self.service.client.describe_feature_type_request(
                type_names=[self.identifier])
        )

        if response.status_code <= 202 and "xml" in response.headers["content-type"]:
            self.describe_feature_type_document = response.content
            if save:
                self.save()
            return self.describe_feature_type_document
        else:
            settings.ROOT_LOGGER.error(
                msg=f"can't fetch describe feature type document. response status code: {
                    response.status_code}; response body: {response.content}"
            )

    def parse(self):
        """Return the parsed self.remote_content

        Raises:
            ValueError: if self.remote_content is null
        """
        if self.describe_feature_type_document:
            mapper = XmlMapper(xml=self.describe_feature_type_document,
                               mapping=XPATH_MAP[("DescribeFeatureType", "2.0.0")])
            mapper.xml_to_django()
            return mapper
        else:
            raise ValueError(
                "there is no fetched content. You need to call fetch_describe_feature_type_document() "
                "first."
            )

    def create_element_instances(self):
        """Return the created FeatureTypeElement record(s)"""
        mapper = self.parse()
        handler = PersistenceHandler(
            mapper=mapper,
            defaults={
                "feature_type_element": {
                    "feature_type": self,
                }
            }
        )
        return handler.persist_all()


class FeatureTypeProperty(models.Model):
    max_occurs = models.IntegerField(default=1, help_text=_(
        "The maximum count this property is part of a feature type"))
    min_occurs = models.IntegerField(default=0, help_text=_(
        "The minimum count this property is part of a feature type"))
    name = models.CharField(max_length=255, help_text=_(
        "The identifing type name of the property"))
    data_type = models.CharField(max_length=255, null=True, blank=True, help_text=_(
        "The concrete data type of this property"))
    required = models.BooleanField(default=False)
    feature_type = models.ForeignKey(
        to=FeatureType,
        editable=False,
        related_name="properties",
        related_query_name="property",
        on_delete=models.CASCADE,
        verbose_name=_("feature type"),
        help_text=_("related feature type of this property"),
    )

    class Meta:
        verbose_name = _("feature type property")
        verbose_name_plural = _("feature type properties")
        ordering = ["-name"]

    def __str__(self):
        return self.name
