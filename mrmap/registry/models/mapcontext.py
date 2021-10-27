from django.contrib.gis.db import models
from django.utils.translation import gettext_lazy as _
from mptt.fields import TreeForeignKey
from mptt.models import MPTTModel
from extras.models import GenericModelMixin, CommonInfo
from registry.models import Layer, DatasetMetadata
from registry.models.metadata import Style


def preview_image_file_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT/xml_documents/<id>/<filename>
    return 'preview_images/{0}/{1}'.format(instance.pk, filename)


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
    dataset_metadata = models.ForeignKey(to=DatasetMetadata,
                                         on_delete=models.PROTECT,
                                         null=True,
                                         blank=True,
                                         verbose_name=_("Dataset Metadata"),
                                         help_text=_("You can use this field to pre filter possible Layer selection."))
    layer = models.ForeignKey(to=Layer,
                              on_delete=models.PROTECT,
                              null=True,
                              blank=True,
                              verbose_name=_("Layer"),
                              help_text=_("Select a layer as a offering for rendering."))
    layer_scale_min = models.FloatField(null=True,
                                        blank=True,
                                        verbose_name=_("scale minimum value"),
                                        help_text=_("minimum scale for a possible request to this layer. If the request is "
                                                    "out of the given scope, the service will response with empty transparent"
                                                    "images. None value means no restriction."))
    layer_scale_max = models.FloatField(null=True,
                                        blank=True,
                                        verbose_name=_("scale maximum value"),
                                        help_text=_("maximum scale for a possible request to this layer. If the request is "
                                                    "out of the given scope, the service will response with empty transparent"
                                                    "images. None value means no restriction."))
    layer_style = models.ForeignKey(to=Style,
                                    on_delete=models.PROTECT,
                                    null=True,
                                    blank=True,
                                    verbose_name=_("Style"),
                                    help_text=_("Select a style for rendering."))
    preview_image = models.ImageField(verbose_name=_("preview image"),
                                      help_text=_("A preview image for the Map Context Layer"),
                                      upload_to=preview_image_file_path,
                                      null=True,
                                      blank=True)

    def __str__(self):
        return f"{self.name}"

    def clean(self):
        if self.layer:
            pass
            # FIXME: TypeError '<' not supported between instances of 'NoneType' and 'float'
            # if self.layer_scale_min < self.layer.inherit_scale_min:
            #     raise ValidationError("configured layer minimum scale can't be smaller than the scale value from the layer.")
            # if self.layer_scale_max > self.layer.inherit_scale_max:
            #     raise ValidationError("configured layer maximum scale can't be greater than the scale value from the layer.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super(MapContextLayer, self).save(*args, **kwargs)

# TODO: The following models are currently unused. Clarify the new structure for map context before enabling them
# class ContextLayerOperations(GenericModelMixin, CommonInfo):
#     map_context_layer = models.ForeignKey(MapContextLayer, on_delete=models.CASCADE)
#     # TODO: CharField of SelectField?
#     # type =
#
#
# class ContextLayerMetadataOptions(GenericModelMixin, CommonInfo):
#     context_layer_operations = models.ForeignKey(ContextLayerOperations, on_delete=models.CASCADE)
#     dataset_metadata = models.ForeignKey(DatasetMetadata,
#                                          on_delete=models.CASCADE,
#                                          null=True,
#                                          blank=True)
#     # TODO: CharField or SelectField?
#     # metadata_format =
#
#
# class ContextLayerRenderOptions(GenericModelMixin, CommonInfo):
#     context_layer_operations = models.ForeignKey(ContextLayerOperations, on_delete=models.CASCADE)
#     # TODO: CharField of SelectField?
#     # type =
#     active = models.BooleanField(null=True, blank=True)
#     minScale = models.IntegerField(null=True, blank=True)
#     maxScale = models.IntegerField(null=True, blank=True)
#     # TODO: in percentage?
#     transparency = models.IntegerField(null=True, blank=True)
#
#
# class ContextLayerSelectOptions(GenericModelMixin, CommonInfo):
#     context_layer_operations = models.ForeignKey(ContextLayerOperations, on_delete=models.CASCADE)
#     layer = models.ForeignKey(Layer, on_delete=models.CASCADE)
#     active = models.BooleanField(null=True, blank=True)
