import os
from django.contrib.gis.geos import Polygon
from django.db import models
from django.contrib.gis.db import models as gis_models
from django.db.models import QuerySet
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.urls import reverse, NoReverseMatch
from MrMap.icons import get_icon, IconEnum
from MrMap.validators import validate_get_capablities_uri
from main.models import GenericModelMixin, CommonInfo
from resourceNew.enums.service import OGCServiceEnum, OGCServiceVersionEnum, HttpMethodEnum, OGCOperationEnum, \
    AuthTypeEnum
from resourceNew.managers.service import ServiceXmlManager, ServiceManager, LayerManager, FeatureTypeElementXmlManager, \
    FeatureTypeManager, FeatureTypeElementManager
from mptt.models import MPTTModel, TreeForeignKey
from uuid import uuid4
from resourceNew.ows_client.request_builder import OgcService
from service.helper.common_connector import CommonConnector
from service.helper.crypto_handler import CryptoHandler
from service.settings import EXTERNAL_AUTHENTICATION_FILEPATH
from resourceNew.parsers.ogc.wfs import DescribedFeatureType as XmlDescribedFeatureType
from eulxml import xmlmap


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


class Service(GenericModelMixin, CommonInfo):
    """ Light polymorph model class to store all registered services. """
    id = models.UUIDField(primary_key=True,
                          default=uuid4,
                          editable=False)
    service_type = models.ForeignKey(to=ServiceType,
                                     on_delete=models.RESTRICT,
                                     editable=False,
                                     related_name="services",
                                     related_query_name="service",
                                     verbose_name=_("service type"),
                                     help_text=_("the concrete type and version of the service."))
    is_active = models.BooleanField(default=False,
                                    verbose_name=_("is active?"),
                                    help_text=_("Used to activate/deactivate the service. If it is deactivated, you "
                                                "cant request the service through the Mr. Map proxy."))
    objects = ServiceManager()
    xml_objects = ServiceXmlManager()

    class Meta:
        verbose_name = _("service")
        verbose_name_plural = _("services")

    def __str__(self):
        if self.metadata:
            return f"{self.metadata.title} ({self.pk})"
        else:
            return str(self.pk)

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
            return reverse(f'{self._meta.app_label}:{self.__class__.__name__.lower()}_{self.service_type_name}_list') \
                   + f'?id__in={self.pk}'
        except NoReverseMatch:
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
    def service_type_name(self):
        return self._service_type.name

    @cached_property
    def service_version(self):
        return self._service_type.version

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


class ExternalAuthentication(CommonInfo):
    username = models.CharField(max_length=255,
                                verbose_name=_("username"),
                                help_text=_("the username used for the authentication."))
    password = models.CharField(max_length=500,
                                verbose_name=_("password"),
                                help_text=_("the password used for the authentication."))
    auth_type = models.CharField(max_length=100,
                                 default=AuthTypeEnum.NONE.value,
                                 choices=AuthTypeEnum.as_choices(),
                                 verbose_name=_("authentication type"),
                                 help_text=_("kind of authentication mechanism shall used."))
    secured_service = models.OneToOneField(to=Service,
                                           on_delete=models.CASCADE,
                                           related_name="external_authentication",
                                           related_query_name="external_authentication",
                                           verbose_name=_("secured service"),
                                           help_text=_("the service which uses this credentials."))
    test_url = models.URLField(validators=[validate_get_capablities_uri],
                               verbose_name=_("Service url"),
                               help_text=_("this shall be the full get capabilities request url."))

    def save(self, register_service=False, *args, **kwargs):
        # todo: if adding, set proxy for the secured_service object
        crypt_handler = CryptoHandler()
        key = crypt_handler.generate_key()
        crypt_handler.write_key_to_file(f"{EXTERNAL_AUTHENTICATION_FILEPATH}/service_{self.secured_service.pk}.key",
                                        key)
        self.encrypt(key)
        super().save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False):
        """ Overwrites default delete function

        Removes local stored file if it exists!

        Args;
            using:
            keep_parents:
        Returns:
        """
        # remove local stored key
        filepath = f"{EXTERNAL_AUTHENTICATION_FILEPATH}/service_{self.secured_service.pk}.key"
        try:
            os.remove(filepath)
        except FileNotFoundError:
            pass
        super().delete(using, keep_parents)

    def encrypt(self, key: str):
        """ Encrypts the login credentials using a given key

        Args:
            key (str):
        Returns:

        """
        crypto_handler = CryptoHandler(msg=self.username, key=key)
        crypto_handler.encrypt()
        self.username = crypto_handler.crypt_message.decode("ascii")

        crypto_handler.message = self.password
        crypto_handler.encrypt()
        self.password = crypto_handler.crypt_message.decode("ascii")

    def decrypt(self, key):
        """ Decrypts the login credentials using a given key

        Args:
            key:
        Returns:

        """
        crypto_handler = CryptoHandler()
        crypto_handler.key = key

        crypto_handler.crypt_message = self.password.encode("ascii")
        crypto_handler.decrypt()
        self.password = crypto_handler.message.decode("ascii")

        crypto_handler.crypt_message = self.username.encode("ascii")
        crypto_handler.decrypt()
        self.username = crypto_handler.message.decode("ascii")


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

    def __str__(self):
        return f"{self.pk} | {self.url} ({self.method})"


class ServiceElement(GenericModelMixin, CommonInfo):
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
                                help_text=_("the main service where this element is part of"))
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
    is_active = models.BooleanField(default=False,
                                    verbose_name=_("is active?"),
                                    help_text=_("Used to activate/deactivate the service. If it is deactivated, you "
                                                "cant request the service through the Mr. Map proxy."))

    class Meta:
        abstract = True

    def __str__(self):
        try:
            return f"{self.metadata.title} ({self.pk})"
        except:
            return str(self.pk)


class Layer(ServiceElement, MPTTModel):
    """ Concrete model class to store parsed layers """
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
        """ Return the bbox of this layer based on the inheritance from other layers as requested in the ogc specs.

            .. note:: excerpt from ogc specs
                **ogc wms 1.1.1**: Every Layer shall have exactly one <LatLonBoundingBox> element that is either stated
                                   explicitly or inherited from a parent Layer. (see section 7.1.4.5.6)
                **ogc wms 1.3.0**: Every named Layer shall have exactly one <EX_GeographicBoundingBox> element that is
                                   either stated explicitly or inherited from a parent Layer. (see section 7.2.4.6.6)

        Returns:
            bbox_lat_lon (geos.Polygon): self.bbox_lat_lon if not None else bbox_lat_lon from the first ancestors where
                                         bbox_lat_lon is not None
        """
        if self.bbox_lat_lon:
            return self.bbox_lat_lon
        else:
            return self.get_ancestors().exclude(bbox_lat_lon=None).values_list("bbox_lat_lon", flat=True).first()

    @cached_property
    def supported_reference_systems(self) -> QuerySet:
        """ Return all supported reference systems for this layer, based on the inheritance from other layers as
            requested in the ogc specs.

            .. note:: excerpt from ogc specs
                **ogc wms 1.1.1**: Every Layer shall have at least one <SRS> element that is either stated explicitly or
                                   inherited from a parent Layer (see section 7.1.4.5.5).
                **ogc wms 1.3.0**: Every Layer is available in one or more layer coordinate reference systems. 6.7.3
                                   discusses the Layer CRS. In order to indicate which Layer CRSs are available, every
                                   named Layer shall have at least one <CRS> element that is either stated explicitly
                                   or inherited from a parent Layer.

        Returns:
            reference_systems (QuerySet): all supported reference systems (ReferenceSystem) for this layer
        """
        from resourceNew.models import ReferenceSystem  # to avoid circular import errors
        return ReferenceSystem.objects.filter(layer__in=self.get_ancestors()).distinct("code", "prefix", "version")

    @cached_property
    def dimensions(self) -> QuerySet:
        """ Return all dimensions of this layer, based on the inheritance from other layers as requested in the ogc
            specs.

            .. note:: excerpt from ogc specs
                **ogc wms 1.1.1**: Dimension declarations are inherited from parent Layers.  Any new Dimension
                                   declarations in the child are added to the list inherited from the parent.
                                   A child **shall not** redefine a Dimension with the same name attribute as one
                                   that was inherited.
                                   Extent declarations are inherited from parent Layers.  Any Extent declarations in
                                   the child with the same name attribute as one inherited from the parent replaces
                                   the value declared by the parent.  A Layer shall not declare an Extent unless a
                                   Dimension with the same name has been declared or inherited earlier in the
                                   Capabilities XML.
                **ogc wms 1.3.0**: Dimension  declarations  are  inherited  from  parent  Layers.  Any  new  Dimension
                                   declaration  in  the  child  with  the  same name attribute as one inherited from
                                   the parent replaces the value declared by the parent.
        """
        from resourceNew.models import Dimension  # to avoid circular import errors
        return Dimension.objects.filter(layer__in=self.get_ancestors(ascending=True)).distinct("name")


class FeatureType(ServiceElement):
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

    def fetch_describe_feature_type_document(self, save=True):
        """ Return the fetched described feature type document and update the content if save is True """
        try:
            external_authentication = self.service.external_authentication
        except ExternalAuthentication.DoesNotExist:
            external_authentication = None
        base_url = self.service.operation_urls.values_list('url', flat=True)\
                                              .get(operation=OGCOperationEnum.DESCRIBE_FEATURE_TYPE.value,
                                                   method=HttpMethodEnum.GET.value)
        link = OgcService(base_url=base_url,
                          service_type=self.service.service_type_name,
                          version=self.service.service_version)\
            .get_describe_feature_type_request(type_name_list=self.identifier).url
        connector = CommonConnector(url=link,
                                    external_auth=external_authentication)
        connector.load()
        content = connector.content
        if isinstance(content, bytes):
            content = str(content, "UTF-8")
        self.describe_feature_type_document = content
        if save:
            self.save()
        return self.describe_feature_type_document

    def parse(self):
        """ Return the parsed self.remote_content

            Raises:
                ValueError: if self.remote_content is null
        """
        if self.describe_feature_type_document:
            parsed_feature_type_elements = xmlmap.load_xmlobject_from_string(string=bytes(self.describe_feature_type_document,
                                                                             "UTF-8"),
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
    maxOccurs = models.IntegerField()
    minOccurs = models.IntegerField()
    name = models.CharField(max_length=255)
    data_type = models.CharField(max_length=255, null=True, blank=True)
    required = models.BooleanField(default=False)
    feature_type = models.ForeignKey(to=FeatureType,
                                     #editable=False,
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


class HarvestResult(CommonInfo):
    pass
