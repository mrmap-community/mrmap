from django.contrib.gis.db import models
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
