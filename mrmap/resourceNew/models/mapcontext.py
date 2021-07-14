from django.contrib.gis.db import models
from mptt.fields import TreeForeignKey
from mptt.models import MPTTModel

from main.models import CommonInfo, GenericModelMixin
from django.utils.translation import gettext_lazy as _


# TODO
class MapContext(GenericModelMixin, CommonInfo):
    title = models.CharField(max_length=1000,
                             null=False,
                             blank=False,
                             verbose_name=_('Title'))
    abstract = models.TextField(null=False,
                                blank=False,
                                verbose_name=_('Abstract'))
    update_date = models.DateTimeField(auto_now_add=True)
    layer_tree = models.TextField(null=False,
                                  blank=False)
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


class MapContextLayer(MPTTModel):
    #map_context = models.ForeignKey(MapContext, on_delete=models.CASCADE)
    title = models.CharField(max_length=1000, null=False, blank=False, verbose_name=_('Title'))
    # parent = models.ForeignKey('self', on_delete=models.CASCADE, blank=True, null=True)
    parent = TreeForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
    # todo referenz auf Dataset (mit Layer)
    # todo referenz auf Layer
    # todo referenz auf FeatureType (zukünftig)
    # zukünftig: featuretype, kml, gml, ...
