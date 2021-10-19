from django import forms
from django.forms import ModelForm, HiddenInput
from django.utils.translation import gettext_lazy as _
from registry.models.mapcontext import MapContext, MapContextLayer
from dal import autocomplete


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
            'dataset_metadata': autocomplete.ModelSelect2(url='registry.autocomplete:dataset_metadata_ac',
                                                          forward=['layer']),
            'layer': autocomplete.ModelSelect2(url='registry.autocomplete:layer_ac',
                                               forward=['dataset_metadata'],),
            'layer_scale_min': forms.widgets.NumberInput()
        }
        fields = [
            'id',
            'parent',
            'parent_form_idx',
            'name',
            'title',
            'dataset_metadata',
            'layer',
            'layer_scale_min',
            'layer_scale_max',
            'preview_image'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current_form_index = self.prefix.split("-")[-1]
        self.fields['layer_scale_min'].widget.attrs['data-bind'] = f'attr: {{ min: selectedLayer{current_form_index}.scale_min }}, enable: Number.isInteger(selectedLayer{current_form_index}.scale_min)'
