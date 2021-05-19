from django.db import models
from django.contrib.gis.db import models as gis_models
from django.contrib.gis.geos import Polygon
from django.utils.translation import gettext_lazy as _
from mptt.models import MPTTModel, TreeForeignKey
from uuid import uuid4

from main.models import GenericModelMixin


class ServiceType(models.Model):
    name = models.CharField(max_length=100,
                            choices=OGCServiceEnum.as_choices())
    version = models.CharField(max_length=100,
                               choices=OGCServiceVersionEnum.as_choices())
    specification = models.URLField(blank=False,
                                    null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['name', 'version'], name='%(app_label)s_%(class)s_unique_name_version')
        ]

    def __str__(self):
        return self.name


class Service(GenericModelMixin, models.Model):
    id = models.UUIDField(primary_key=True,
                          default=uuid4,
                          editable=False)
    service_type = models.ForeignKey(ServiceType,
                                     on_delete=models.DO_NOTHING,
                                     null=True,
                                     blank=True)

    class Meta:
        verbose_name = _("service")
        verbose_name_plural = _("services")


class Layer(GenericModelMixin, MPTTModel):
    id = models.UUIDField(primary_key=True,
                          default=uuid4,
                          editable=False)
    service = models.ForeignKey(to=Service,
                                on_delete=models.CASCADE,
                                related_name="layers",
                                related_query_name="layer",
                                verbose_name=_("parent service"),
                                help_text=_("choice the service where this layer is part from"))
    parent = TreeForeignKey(to="self",
                            on_delete=models.CASCADE,
                            null=True,
                            blank=True,
                            related_name="children",
                            related_query_name="child",
                            verbose_name=_("parent layer"))
    identifier = models.CharField(max_length=500,
                                  null=True,
                                  blank=True)
    is_queryable = models.BooleanField(default=False)
    is_opaque = models.BooleanField(default=False)
    is_cascaded = models.BooleanField(default=False)
    scale_min = models.FloatField(default=0)
    scale_max = models.FloatField(default=0)
    bbox_lat_lon = gis_models.PolygonField(default=Polygon(
        (
            (-90.0, -180.0),
            (-90.0, 180.0),
            (90.0, 180.0),
            (90.0, -180.0),
            (-90.0, -180.0),
        )
    ))

    class Meta:
        verbose_name = _("layer")
        verbose_name_plural = _("layers")


class FeatureType(GenericModelMixin, models.Model):
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


class HarvestResult(models.Model):
    pass
