from django.forms import BaseInlineFormSet
from extra_views import InlineFormSetFactory

from resourceNew.forms.mapcontext import MapContextLayerForm
from resourceNew.models.mapcontext import MapContextLayer


class MapContextLayerInline(InlineFormSetFactory):
    model = MapContextLayer
    # TODO cannot switch to form_class ("__init__() missing 1 required positional argument: 'request'"...)
    form_class = MapContextLayerForm
    #fields = '__all__'
    prefix = 'layer'
    #factory_kwargs = {'extra': 1, 'can_delete': True, 'formset': LayerTreeInlineFormSet}
    factory_kwargs = {'extra': 1, 'can_delete': True, 'formset': BaseInlineFormSet}
