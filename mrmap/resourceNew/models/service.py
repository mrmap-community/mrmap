from django.db import models
from django.contrib.gis.db import models as gis_models
from django.contrib.gis.geos import Polygon
from django.utils.translation import gettext_lazy as _
from main.models import GenericModelMixin, CommonInfo
from resourceNew.enums.service import OGCServiceEnum, OGCServiceVersionEnum, HttpMethodEnum, OGCOperationEnum
from resourceNew.managers.service import ServiceXmlManager
from mptt.models import MPTTModel, TreeForeignKey
from uuid import uuid4


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
                                    verbose_name=_("is active"),
                                    help_text=_("Used to activate/deactivate the service. If it is deactivated, you "
                                                "cant request the resource through the Mr. Map proxy."))

    objects = ServiceXmlManager()

    class Meta:
        verbose_name = _("service")
        verbose_name_plural = _("services")


class OperationUrl(models.Model):
    """ Concrete model class to store operation urls for registered services """
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
    service = models.ForeignKey(to=Service,
                                on_delete=models.CASCADE,
                                editable=False,
                                related_name="operation_urls",
                                related_query_name="operation_url",
                                verbose_name=_("related service"),
                                help_text=_("the service for that this url can be used for."))

    def __str__(self):
        return f"{self.pk} | {self.url} ({self.method})"


class Layer(GenericModelMixin, CommonInfo, MPTTModel):
    """ Concrete model class to store parsed layers """
    id = models.UUIDField(primary_key=True,
                          default=uuid4,
                          editable=False)
    service = models.ForeignKey(to=Service,
                                on_delete=models.CASCADE,
                                editable=False,
                                related_name="layers",
                                related_query_name="layer",
                                verbose_name=_("parent service"),
                                help_text=_("the main service where this layer is part of"))
    parent = TreeForeignKey(to="self",
                            on_delete=models.CASCADE,
                            null=True,
                            editable=False,
                            related_name="children",
                            related_query_name="child",
                            verbose_name=_("parent layer"),
                            help_text=_("the ancestor of this layer."))
    identifier = models.CharField(max_length=500,
                                  null=True,
                                  blank=True)
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
                                  verbose_name=_("scale minimum value"),
                                  help_text=_("minimum scale for a possible request to this layer. If the request is "
                                              "out of the given scope, the service will response with empty transparent"
                                              "images. None value means no restriction."))
    scale_max = models.FloatField(null=True,
                                  blank=True,
                                  verbose_name=_("scale maximum value"),
                                  help_text=_("maximum scale for a possible request to this layer. If the request is "
                                              "out of the given scope, the service will response with empty transparent"
                                              "images. None value means no restriction."))
    bbox_lat_lon = gis_models.PolygonField(default=Polygon(((-90.0, -180.0), (-90.0, 180.0),
                                                            (90.0, 180.0), (90.0, -180.0), (-90.0, -180.0),)),
                                           editable=False,
                                           verbose_name=_("bounding box"),
                                           help_text=_("the spatial area for that the layer response with concrete "
                                                       "data."))

    class Meta:
        verbose_name = _("layer")
        verbose_name_plural = _("layers")


class MimeType(models.Model):
    mime_type = models.CharField(max_length=500,
                                 unique=True,
                                 db_index=True,
                                 verbose_name=_("mime type"),
                                 help_text=_("The Internet Media Type"))

    def __str__(self):
        return self.mime_type


class Style(models.Model):
    layer = models.ForeignKey(to=Layer,
                              on_delete=models.CASCADE,
                              editable=False,
                              verbose_name=_("related layer"),
                              help_text=_("the layer for that this style is for."),
                              related_name="styles",
                              related_query_name="style")
    name = models.CharField(max_length=255,
                            editable=False,
                            verbose_name=_("name"),
                            help_text=_("The style's Name is used in the Map request STYLES parameter to lookup the "
                                        "style on server side."))
    title = models.CharField(max_length=255,
                             editable=False,
                             verbose_name=_("title"),
                             help_text=_("The Title is a human-readable string as an alternative for the name "
                                         "attribute."))

    def __str__(self):
        return self.layer.identifier + ": " + self.name


class LegendUrl(models.Model):
    legend_url = models.URLField(max_length=4096,
                                 editable=False,
                                 help_text=_("contains the location of an image of a map legend appropriate to the "
                                             "enclosing Style."))
    height = models.IntegerField(editable=False,
                                 help_text=_("the size of the image in pixels"))
    width = models.IntegerField(editable=False,
                                help_text=_("the size of the image in pixels"))
    mime_type = models.ForeignKey(to=MimeType,
                                  on_delete=models.PROTECT,
                                  editable=False,
                                  related_name="legend_urls",
                                  related_query_name="legend_url",
                                  verbose_name=_("internet mime type"),
                                  help_text=_("the mime type of the remote legend url"))
    style = models.OneToOneField(to=Style,
                                 on_delete=models.CASCADE,
                                 editable=False,
                                 verbose_name=_("related style"),
                                 help_text=_("the style entity which is linked to this legend url"),
                                 related_name="legend_url",
                                 related_query_name="legend_url")


class FeatureType(GenericModelMixin, CommonInfo):
    id = models.UUIDField(primary_key=True,
                          default=uuid4,
                          editable=False)
    service = models.ForeignKey(to=Service,
                                on_delete=models.CASCADE,
                                related_name="feature_types",
                                related_query_name="feature_type")

    class Meta:
        verbose_name = _("feature type")
        verbose_name_plural = _("feature types")


class HarvestResult(CommonInfo):
    pass
