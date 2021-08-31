from django.contrib.gis.db import models
from mptt.fields import TreeForeignKey
from mptt.models import MPTTModel

from main.models import CommonInfo, GenericModelMixin
from django.utils.translation import gettext_lazy as _


class MapContext(CommonInfo, GenericModelMixin):
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
    #map_context = models.ForeignKey(MapContext, on_delete=models.CASCADE)
    title = models.CharField(max_length=1000, null=False, blank=False, verbose_name=_('Title'))
    # parent = models.ForeignKey('self', on_delete=models.CASCADE, blank=True, null=True)
    parent = TreeForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
    # todo referenz auf Dataset (mit Layer)
    # todo referenz auf Layer
    # todo referenz auf FeatureType (zukünftig)
    # zukünftig: featuretype, kml, gml, ...
