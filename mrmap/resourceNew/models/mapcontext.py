from django.contrib.gis.db import models
from django.utils.translation import gettext_lazy as _
from mptt.fields import TreeForeignKey
from mptt.models import MPTTModel

from main.models import GenericModelMixin, CommonInfo
from resourceNew.models import DatasetMetadata, LayerMetadata, FeatureTypeMetadata, Layer
from resourceNew.models.document import preview_image_file_path


class MapContext(GenericModelMixin, CommonInfo):
    title = models.CharField(max_length=1000,
                             verbose_name=_("title"),
                             help_text=_("a short descriptive title for this map context"))
    abstract = models.TextField(null=True,
                                verbose_name=_("abstract"),
                                help_text=_("brief summary of the topic of this map context"))

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

    def __str__(self):
        return self.title


class MapContextLayer(MPTTModel):
    parent = TreeForeignKey("MapContextLayer", on_delete=models.CASCADE, null=True, blank=True,
                            related_name="child_layers")
    map_context = models.ForeignKey(MapContext, on_delete=models.CASCADE)
    name = models.CharField(max_length=1000,
                            null=False,
                            blank=False,
                            verbose_name=_("name"),
                            help_text=_("an identifying name for this map context layer"))
    title = models.CharField(max_length=1000,
                             null=True,
                             blank=True,
                             verbose_name=_("title"),
                             help_text=_("a short descriptive title for this map context layer"))
    # TODO: Move to ContextLayerMetadataOptions
    dataset_metadata = models.ForeignKey(DatasetMetadata,
                                         on_delete=models.CASCADE,
                                         null=True,
                                         blank=True)
    # TODO: Move to ContextLayerSelectOptions
    layer = models.ForeignKey(Layer,
                              on_delete=models.CASCADE,
                              null=True,
                              blank=True)

    preview_image = models.ImageField(verbose_name=_("preview image"),
                                      help_text=_("A preview image for the Map Context Layer"),
                                      upload_to=preview_image_file_path,
                                      null=True,
                                      blank=True)

    def __str__(self):
        return f"{self.name}"


class ContextLayerOperations(GenericModelMixin, CommonInfo):
    map_context_layer = models.ForeignKey(MapContextLayer, on_delete=models.CASCADE)
    # TODO: CharField of SelectField?
    # type =


class ContextLayerMetadataOptions(GenericModelMixin, CommonInfo):
    context_layer_operations = models.ForeignKey(ContextLayerOperations, on_delete=models.CASCADE)
    dataset_metadata = models.ForeignKey(DatasetMetadata,
                                         on_delete=models.CASCADE,
                                         null=True,
                                         blank=True)
    # TODO: CharField or SelectField?
    # metadata_format =


class ContextLayerRenderOptions(GenericModelMixin, CommonInfo):
    context_layer_operations = models.ForeignKey(ContextLayerOperations, on_delete=models.CASCADE)
    # TODO: CharField of SelectField?
    # type =
    active = models.BooleanField(null=True, blank=True)
    minScale = models.IntegerField(null=True, blank=True)
    maxScale = models.IntegerField(null=True, blank=True)
    # TODO: in percentage?
    transparency = models.IntegerField(null=True, blank=True)


class ContextLayerSelectOptions(GenericModelMixin, CommonInfo):
    context_layer_operations = models.ForeignKey(ContextLayerOperations, on_delete=models.CASCADE)
    layer = models.ForeignKey(Layer, on_delete=models.CASCADE)
    active = models.BooleanField(null=True, blank=True)
