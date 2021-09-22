from dal import autocomplete
from django import forms
from django.forms import ModelForm, HiddenInput
from django.utils.translation import gettext_lazy as _

from resourceNew.models.mapcontext import MapContext, MapContextLayer


class MapContextForm(ModelForm):
    abstract = forms.CharField(label=_('Abstract'), help_text=_("brief summary of the topic of this map context"))

    class Meta:
        model = MapContext
        fields = ('title', 'abstract')


class MapContextLayerForm(ModelForm):
    parent_form_idx = forms.CharField(required=False, widget=HiddenInput)

    class Meta:
        model = MapContextLayer
        widgets = {
            'parent': HiddenInput(),
            # TODO: With the widget is not working. Something missing in template???
            'dataset_metadata': autocomplete.ModelSelect2(url='resourceNew.autocomplete:dataset_metadata_ac'),
            # TODO: Layer metadata should only appear and be filtered by the selected dataset metadata
            # 'layer_metadata': autocomplete.ModelSelect2(url='resourceNew.autocomplete:layer_metadata_ac')
        }
        fields = [
            'id',
            'parent',
            'parent_form_idx',
            'name',
            'title',
            'dataset_metadata',
            'layer_metadata'
        ]

