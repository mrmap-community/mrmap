from uuid import uuid4

from django.conf import settings
from django.contrib.gis.db import models as gis_models
from django.contrib.gis.geos import Polygon
from django.db import models
from django.db.models import QuerySet
from django.urls import reverse, NoReverseMatch
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from eulxml import xmlmap
from mptt.models import MPTTModel, TreeForeignKey
from requests import Session
from requests.auth import HTTPDigestAuth

from MrMap.icons import get_icon, IconEnum
from MrMap.settings import PROXIES
from extras.models import GenericModelMixin, CommonInfo
from extras.utils import camel_to_snake
from ows_client.request_builder import OgcService
from registry.enums.service import OGCServiceEnum, OGCServiceVersionEnum, HttpMethodEnum, OGCOperationEnum, \
    AuthTypeEnum
from registry.managers.security import ServiceSecurityManager, OperationUrlManager
from registry.managers.service import ServiceXmlManager, ServiceManager, LayerManager, FeatureTypeElementXmlManager, \
    FeatureTypeManager, FeatureTypeElementManager
from registry.models.document import CapabilitiesDocumentModelMixin
from registry.models.metadata import FeatureTypeMetadata, LayerMetadata, ServiceMetadata
from registry.xmlmapper.ogc.wfs_describe_feature_type import DescribedFeatureType as XmlDescribedFeatureType


class ServiceType(models.Model):
    """ Concrete model class to store different service types such as wms 1.1.1, csw 2.0.2... """
    name = models.CharField(max_length=10,
                            choices=OGCServiceEnum.as_choices(),
                            editable=False,
                            verbose_name=_("type"),
                            help_text=_("the concrete type name of the service type."))
    version = models.CharField(max_length=10,
                               choices=OGCServiceVersionEnum.as_choices(),
                               editable=False,
                               verbose_name=_("version"),
                               help_text=_("the version of the service type as sem version"))
    specification = models.URLField(null=True,
                                    editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['name', 'version'],
                                    name='%(app_label)s_%(class)s_unique_name_version')
        ]

    def __str__(self):
        return self.name


class CommonServiceInfo(models.Model):
    hits = models.PositiveIntegerField(default=0,
                                       editable=False,
                                       verbose_name=_("hits"),
                                       help_text=_("how many times this metadata was requested by a client"), )
    is_active = models.BooleanField(default=False,
                                    verbose_name=_("is active?"),
                                    help_text=_("Used to activate/deactivate the service. If it is deactivated, you "
                                                "cant request the service through the Mr. Map proxy."))

    class Meta:
        abstract = True


class Service(CapabilitiesDocumentModelMixin, GenericModelMixin, ServiceMetadata, CommonServiceInfo, CommonInfo):
    """ Light polymorph model class to store all registered services. """
    service_type = models.ForeignKey(to=ServiceType,
                                     on_delete=models.PROTECT,
                                     editable=False,
                                     related_name="services",
                                     related_query_name="service",
                                     verbose_name=_("service type"),
                                     help_text=_("the concrete type and version of the service."))
    url = models.URLField(max_length=4096,
                          editable=False,
                          verbose_name=_("url"),
                          help_text=_("the base url of the service"))
    objects = ServiceManager()
    security = ServiceSecurityManager()
    xml_objects = ServiceXmlManager()

    # todo:
    xml_mapper_cls = None

    class Meta:
        verbose_name = _("service")
        verbose_name_plural = _("services")

    def save(self, *args, **kwargs):
        adding = self._state.adding
        old = None
        if not adding:
            old = Service.objects.filter(pk=self.pk).first()
        super().save(*args, **kwargs)
        if not adding and old and old.is_active != self.is_active:
            # the active sate of this and all descendant elements shall be changed to the new value. Bulk update
            # is the most efficient way to do it.
            if self.is_service_type(OGCServiceEnum.WMS):
                self.layers.update(is_active=self.is_active)
            elif self.is_service_type(OGCServiceEnum.WFS):
                self.featuretypes.update(is_active=self.is_active)

    def get_absolute_url(self) -> str:
        try:
            return reverse(
                f'{self._meta.app_label}:{camel_to_snake(self.__class__.__name__)}_{self.service_type_name}_view',
                args=[self.pk, ])
        except NoReverseMatch:
            return self.get_concrete_table_url()

    def get_concrete_table_url(self) -> str:
        try:
            return reverse(
                f'{self._meta.app_label}:{camel_to_snake(self.__class__.__name__)}_{self.service_type_name}_list') + f'?id__in={self.pk}'
        except NoReverseMatch:
            return ""

    def get_tree_view_url(self) -> str:
        try:
            return reverse(
                f'{self._meta.app_label}:{self.__class__.__name__.lower()}_{self.service_type_name}_tree_view',
                args=[self.pk])
        except NoReverseMatch:
            return ""

    def get_activate_url(self) -> str:
        try:
            return reverse(f'{self._meta.app_label}:{self.__class__.__name__.lower()}_activate', args=[self.pk])
        except NoReverseMatch:
            return ""

    def get_harvest_url(self) -> str:
        if self.is_service_type(OGCServiceEnum.CSW):
            try:
                return reverse(f'{self._meta.app_label}:{self.__class__.__name__.lower()}_harvest', args=[self.pk])
            except NoReverseMatch:
                pass
        return ""

    @property
    def icon(self):
        try:
            return get_icon(getattr(IconEnum, self.service_type_name.upper()))
        except AttributeError:
            return ""

    @cached_property
    def _service_type(self):
        return self.service_type

    @cached_property
    def service_type_name(self) -> str:
        return self._service_type.name

    @cached_property
    def service_version(self) -> str:
        return self._service_type.version

    @cached_property
    def major_service_version(self) -> int:
        return int(self.service_version.split('.')[0])

    @cached_property
    def minor_service_version(self) -> int:
        return int(self.service_version.split('.')[1])

    @cached_property
    def fix_service_version(self) -> int:
        return int(self.service_version.split('.')[2])

    def is_service_type(self, name: OGCServiceEnum):
        """ Return True if the given service type name matches else return None

            Returns:
                True|False (boolean)
        """
        if self.service_type_name == name.value:
            return True
        else:
            return False

    @cached_property
    def root_layer(self):
        if self.is_service_type(OGCServiceEnum.WMS):
            return self.layers.get(parent=None)
        else:
            return None

    def get_session_for_request(self) -> Session:
        session = Session()
        session.proxies = PROXIES
        if hasattr(self, "external_authentication"):
            session.auth = self.external_authentication.get_auth_for_request()
        return session


class OperationUrl(CommonInfo):
    """ Concrete model class to store operation urls for registered services

        With that urls we can perform all needed request to a given service.
    """
    method = models.CharField(max_length=10,
                              choices=HttpMethodEnum.as_choices(),
                              verbose_name=_("http method"),
                              help_text=_("the http method you can perform for this url"))
    # 2048 is the technically specified max length of an url. Some services urls scratches this limit.
    url = models.URLField(max_length=4096,
                          editable=False,
                          verbose_name=_("url"),
                          help_text=_("the url for this operation"))
    operation = models.CharField(max_length=30,
                                 choices=OGCOperationEnum.as_choices(),
                                 editable=False,
                                 verbose_name=_("operation"),
                                 help_text=_("the operation you can perform with this url."))
    mime_types = models.ManyToManyField(to="MimeType",  # use string to avoid from circular import error
                                        blank=True,
                                        editable=False,
                                        related_name="operation_urls",
                                        related_query_name="operation_url",
                                        verbose_name=_("internet mime type"),
                                        help_text=_("all available mime types of the remote url"))
    service = models.ForeignKey(to=Service,
                                on_delete=models.CASCADE,
                                editable=False,
                                related_name="operation_urls",
                                related_query_name="operation_url",
                                verbose_name=_("related service"),
                                help_text=_("the service for that this url can be used for."))
    objects = models.Manager()
    security_objects = OperationUrlManager()

    def __str__(self):
        return f"{self.pk} | {self.url} ({self.method})"

    @property
    def concrete_url(self):
        return f'{reverse("registry:service_operation_view", args=[self.service_id, ])}?REQUEST={self.operation}&VERSION={self.service.service_version}'


class ServiceElement(CapabilitiesDocumentModelMixin, GenericModelMixin, CommonServiceInfo, CommonInfo):
    """ Abstract model class to generalize some fields and functions for layers and feature types """
    id = models.UUIDField(primary_key=True,
                          default=uuid4,
                          editable=False)
    service = models.ForeignKey(to=Service,
                                on_delete=models.CASCADE,
                                editable=False,
                                related_name="%(class)ss",
                                related_query_name="%(class)s",
                                verbose_name=_("parent service"),
                                help_text=_("the extras service where this element is part of"))
    identifier = models.CharField(max_length=500,
                                  null=True,
                                  editable=False,
                                  verbose_name=_("identifier"),
                                  help_text=_("this is a string which identifies the element on the remote service."))
    bbox_lat_lon = gis_models.PolygonField(null=True,  # to support inherited bbox from ancestor layer null=True
                                           blank=True,
                                           editable=False,
                                           verbose_name=_("bounding box"),
                                           help_text=_("bounding box shall be supplied regardless of what CRS the map "
                                                       "server may support, but it may be approximate if the data are "
                                                       "not natively in geographic coordinates. The purpose of bounding"
                                                       " box is to facilitate geographic searches without requiring "
                                                       "coordinate transformations by the search engine."))
    reference_systems = models.ManyToManyField(to="ReferenceSystem",  # to avoid circular import error
                                               related_name="%(class)s",
                                               related_query_name="%(class)s",
                                               blank=True,
                                               editable=False,
                                               verbose_name=_("reference systems"),
                                               help_text=_("all reference systems which this element supports"))
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
                return reverse(f'{self._meta.app_label}:dataset_metadata_list') + \
                    f'?id__in={",".join([str(dataset.pk) for dataset in self.dataset_metadata.all()])}'
            except NoReverseMatch:
                pass
        return ""


class Layer(LayerMetadata, ServiceElement, MPTTModel):
    """Concrete model class to store parsed layers.

    :attr objects: custom models manager :class:`registry.managers.service.LayerManager`
    """
    parent = TreeForeignKey(to="self",
                            on_delete=models.CASCADE,
                            null=True,
                            editable=False,
                            related_name="children",
                            related_query_name="child",
                            verbose_name=_("parent layer"),
                            help_text=_("the ancestor of this layer."))
    is_queryable = models.BooleanField(default=False,
                                       editable=False,
                                       verbose_name=_("is queryable"),
                                       help_text=_("flag to signal if this layer provides factual information or not."
                                                   " Parsed from capabilities."))
    is_opaque = models.BooleanField(default=False,
                                    editable=False,
                                    verbose_name=_("is opaque"),
                                    help_text=_("flag to signal if this layer support transparency content or not. "
                                                "Parsed from capabilities."))
    is_cascaded = models.BooleanField(default=False,
                                      editable=False,
                                      verbose_name=_("is cascaded"),
                                      help_text=_("WMS cascading allows to expose layers coming from other WMS servers "
                                                  "as if they were local layers"))
    scale_min = models.FloatField(null=True,
                                  blank=True,
                                  editable=False,
                                  verbose_name=_("scale minimum value"),
                                  help_text=_("minimum scale for a possible request to this layer. If the request is "
                                              "out of the given scope, the service will response with empty transparent"
                                              "images. None value means no restriction."))
    scale_max = models.FloatField(null=True,
                                  blank=True,
                                  editable=False,
                                  verbose_name=_("scale maximum value"),
                                  help_text=_("maximum scale for a possible request to this layer. If the request is "
                                              "out of the given scope, the service will response with empty transparent"
                                              "images. None value means no restriction."))

    class Meta:
        verbose_name = _("layer")
        verbose_name_plural = _("layers")

    objects = LayerManager()

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
                Service.objects.filter(pk=self.service_id).update(is_active=self.is_active)
            else:
                self.get_descendants().update(is_active=self.is_active)

    @cached_property
    def bbox(self) -> Polygon:
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
            return self.get_ancestors().exclude(bbox_lat_lon=None).values_list("bbox_lat_lon", flat=True).first()

    @cached_property
    def supported_reference_systems(self) -> QuerySet:
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
        from registry.models import ReferenceSystem  # to avoid circular import errors
        return ReferenceSystem.objects.filter(layer__in=self.get_ancestors()).distinct("code", "prefix", "version")

    @cached_property
    def dimensions(self) -> QuerySet:
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
        from registry.models import Dimension  # to avoid circular import errors
        return Dimension.objects.filter(layer__in=self.get_ancestors(ascending=True)).distinct("name")


class FeatureType(FeatureTypeMetadata, ServiceElement):
    """Concrete model class to store parsed FeatureType.

    :attr objects: custom models manager :class:`registry.managers.service.FeatureTypeManager`
    """
    output_formats = models.ManyToManyField(to="MimeType",  # use string to avoid from circular import error
                                            blank=True,
                                            editable=False,
                                            related_name="feature_types",
                                            related_query_name="feature_type",
                                            verbose_name=_("output formats"),
                                            help_text=_("This is a list of MIME types indicating the output formats "
                                                        "that may be generated for a feature type.  If this optional "
                                                        "element is not specified, then all the result formats "
                                                        "listed for the GetFeature operation are assumed to be "
                                                        "supported. "))
    describe_feature_type_document = models.TextField(null=True,
                                                      verbose_name=_("describe feature type"),
                                                      help_text=_("the fetched content of the download describe feature"
                                                                  " type document."))
    objects = FeatureTypeManager()

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
            Service.objects.filter(pk=self.service_id).update(is_active=self.is_active)

    def fetch_describe_feature_type_document(self, save=True):
        """ Return the fetched described feature type document and update the content if save is True """
        base_url = self.service.operation_urls.values_list('url', flat=True) \
            .get(operation=OGCOperationEnum.DESCRIBE_FEATURE_TYPE.value,
                 method=HttpMethodEnum.GET.value)
        request = OgcService(base_url=base_url,
                             service_type=self.service.service_type_name,
                             version=self.service.service_version) \
            .get_describe_feature_type_request(type_name_list=self.identifier)
        if hasattr(self.service, "external_authentication"):
            username, password = self.service.external_authentication.decrypt()
            if self.service.external_authentication.auth_type == AuthTypeEnum.BASIC.value:
                request.auth = (username, password)
            elif self.service.external_authentication.auth_type == AuthTypeEnum.DIGEST.value:
                request.auth = HTTPDigestAuth(username=username,
                                              password=password)
        session = Session()
        response = session.send(request=request.prepare())
        if response.status_code <= 202 and "xml" in response.headers["content-type"]:
            self.describe_feature_type_document = response.content
            if save:
                self.save()
            return self.describe_feature_type_document
        else:
            settings.ROOT_LOGGER.error(
                msg=f"can't fetch describe feature type document. response status code: {response.status_code}; response body: {response.content}")

    def parse(self):
        """ Return the parsed self.remote_content

            Raises:
                ValueError: if self.remote_content is null
        """
        if self.describe_feature_type_document:
            parsed_feature_type_elements = xmlmap.load_xmlobject_from_string(string=self.describe_feature_type_document,
                                                                             xmlclass=XmlDescribedFeatureType)
            return parsed_feature_type_elements
        else:
            raise ValueError("there is no fetched content. You need to call fetch_describe_feature_type_document() "
                             "first.")

    def create_element_instances(self):
        """ Return the created FeatureTypeElement record(s) """
        return FeatureTypeElement.xml_objects.create_from_parsed_xml(parsed_xml=self.parse(),
                                                                     related_object=self)


class FeatureTypeElement(CommonInfo):
    max_occurs = models.IntegerField(default=1)
    min_occurs = models.IntegerField(default=0)
    name = models.CharField(max_length=255)
    data_type = models.CharField(max_length=255, null=True, blank=True)
    required = models.BooleanField(default=False)
    feature_type = models.ForeignKey(to=FeatureType,
                                     # editable=False,
                                     related_name="elements",
                                     related_query_name="element",
                                     on_delete=models.CASCADE,
                                     verbose_name=_("feature type"),
                                     help_text=_("related feature type of this element"))
    objects = FeatureTypeElementManager()
    xml_objects = FeatureTypeElementXmlManager()

    class Meta:
        verbose_name = _("feature type element")
        verbose_name_plural = _("feature type elements")
        ordering = ["-name"]

    def __str__(self):
        return self.name
