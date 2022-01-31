from django.contrib.gis.db import models
from django.contrib.gis.geos import Polygon
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from mptt.fields import TreeForeignKey
from mptt.models import MPTTModel
from registry.managers.mapcontext import MapContextManager
from registry.models import DatasetMetadata, Layer
from registry.models.metadata import Style


def preview_image_file_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT/xml_documents/<id>/<filename>
    return 'preview_images/{0}/{1}'.format(instance.pk, filename)


class MapContext(models.Model):
    title: str = models.CharField(
        max_length=1000,
        verbose_name=_("title"),
        help_text=_("a short descriptive title for this map context"))
    abstract: str = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("abstract"),
        help_text=_("brief summary of the topic of this map context"))
    pixel_width: int = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("pixel width")
    )
    pixel_height: int = models.PositiveIntegerField(
        null=True,
        blank=True,
    )
    mm_per_pixel: float = models.FloatField(
        null=True,
        blank=True,
    )
    bbox: Polygon = models.PolygonField(
        null=True,
        blank=True,
    )

    # Additional possible parameters:
    # specReference
    # language
    # author
    # publisher
    # creator
    # rights
    # areaOfInterest
    # timeIntervalOfInterest
    # keyword
    # resource
    # contextMetadata
    # extension

    objects = MapContextManager()

    def __str__(self):
        return self.title

    def as_ows_context(self):
        ows_context = {
            "type": "FeatureCollection",
            "id": reverse("ows-context-detail", args=[self.pk]),
            "properties": {
                "title": self.title,
                "subtilte": self.abstract,
                "display": {
                    "pixelWidth": self.pixel_width,
                    "pixelHeight": self.pixel_height,
                    "mmPerPixel": self.mm_per_pixel
                }

            },
            "bbox": list(self.bbox.extent),
            "features": [context_layer.as_ows_feature() for context_layer in self.child_layers.all()]
        }
        return ows_context


class RenderingOffering(models.Model):
    rendering_layer = models.ForeignKey(
        to=Layer,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="mapcontextlayers_rendering",
        verbose_name=_("Rendering layer"),
        help_text=_("Select a layer for rendering."))
    layer_scale_min = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("scale minimum value"),
        help_text=_(
            "minimum scale for a possible request to this layer. If the request is "
            "out of the given scope, the service will response with empty transparent"
            "images. None value means no restriction."))
    layer_scale_max = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("scale maximum value"),
        help_text=_(
            "maximum scale for a possible request to this layer. If the request is "
            "out of the given scope, the service will response with empty transparent"
            "images. None value means no restriction."))
    layer_style = models.ForeignKey(
        to=Style,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_("Style"),
        help_text=_("Select a style for rendering."))
    preview_image = models.ImageField(
        verbose_name=_("preview image"),
        help_text=_(
            "A preview image for the Map Context Layer"),
        upload_to=preview_image_file_path,
        null=True,
        blank=True)
    active = models.BooleanField(
        verbose_name=_("active"),
        help_text=_("should this offering be visible?"))
    # transparency = models.IntegerField(
    #     null=True,
    #     blank=True)

    class Meta:
        abstract = True

    def clean(self):
        errors = {}
        if self.rendering_layer:
            # TODO: move this to checkContraints
            # Check scale min/max values against the possible configureable values.
            if self.layer_scale_min and self.layer.inherit_scale_min:
                if self.layer_scale_min < self.layer.inherit_scale_min:
                    errors.update({'layer_scale_min': ValidationError(
                        "configured layer minimum scale can't be smaller than the scale value of the layer.")})
                if self.layer_scale_min > self.layer.inherit_scale_max:
                    errors.update({'layer_scale_min': ValidationError(
                        "configured layer minimum scale can't be greater than the maximum scale value of the layer.")})
            if self.layer_scale_max and self.layer.inherit_scale_max:
                if self.layer_scale_max > self.layer.inherit_scale_max:
                    errors.update({'layer_scale_max': ValidationError(
                        "configured layer maximum scale can't be greater than the scale value of the layer.")})
                if self.layer_scale_max < self.layer.inherit_scale_max:
                    errors.update({'layer_scale_max': ValidationError(
                        "configured layer maximum scale can't be smaller than the minimum scale value of the layer.")})

            # Check style configuration
            if self.layer_style and not self.layer.styles.filter(pk=self.layer_style.pk).exists():
                errors.update({'layer_style': ValidationError(
                    "configured style is not a valid style for the selected layer.")})

        if errors:
            raise ValidationError(errors)

    def as_ows_offering(self):
        return {
            "code": "http://www.opengis.net/spec/owc-atom/1.0/req/wms",
            "operations": [
                {
                    "code": "GetMap",
                    "method": "GET",
                    "type": "image/png",
                    "href": "TODO",
                    "extensions": {
                        "active": self.active
                    }
                }
            ]
        }


class SelectionOffering(models.Model):
    selection_layer = models.ForeignKey(
        to=Layer,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="mapcontextlayers_selection",
        verbose_name=_("Selection layer"),
        help_text=_("Select a layer for feature selection."))


class MapContextLayer(RenderingOffering, SelectionOffering, MPTTModel):
    parent = TreeForeignKey(
        to="MapContextLayer",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="child_layers",
        releated_query_name="child_layer")
    map_context = models.ForeignKey(
        to=MapContext,
        on_delete=models.CASCADE,
        related_name='map_context_layers',
        related_query_name='map_context_layer')
    title = models.CharField(
        max_length=1000,
        null=False,
        blank=False,
        verbose_name=_("title"),
        help_text=_("an identifying name for this map context layer"))
    description = models.CharField(
        max_length=1000,
        null=True,
        blank=True,
        verbose_name=_("description"),
        help_text=_("a short description for this map context layer"))
    dataset_metadata = models.ForeignKey(
        to=DatasetMetadata,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_("Dataset Metadata"),
        help_text=_("You can use this field to pre filter possible Layer selection."))

    def __str__(self):
        return f"{self.name}"

    def save(self, *args, **kwargs):
        self.full_clean()
        return super(MapContextLayer, self).save(*args, **kwargs)

    def as_ows_feature(self) -> dict:
        ows_feature = {
            "type": "Feature",
            "offerings": self._ows_offerings,
            "properties": {
                "title": self.title,
                "abstract": self.abstract,
                "minScaleDenominator": self.layer_scale_min,
                "maxScaleDenominator": self.layer_scale_max,
                "updated": "TODO",
                "folder": "TODO"
            }
        }
        return ows_feature
