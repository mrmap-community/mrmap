from dal import autocomplete
from django import forms
from django.forms import ModelForm, HiddenInput
from django.utils.translation import gettext_lazy as _

from resourceNew.models import LayerMetadata, DatasetMetadataRelation
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
            'dataset_metadata': autocomplete.ModelSelect2(url='resourceNew.autocomplete:dataset_metadata_ac'),
            # TODO: Layer metadata should only appear and be filtered by the selected dataset metadata
            #'layer_metadata': autocomplete.ModelSelect2(url='resourceNew.autocomplete:layer_metadata_ac')
        }
        fields = [
            'id',
            'parent',
            'parent_form_idx',
            'name',
            'title',
            'dataset_metadata',
            #'layer_metadata'
            'preview_image'
        ]

       # def __init__(self, *args, **kwargs):
       #     super().__init__(*args, **kwargs)
       #     dataset_metadata_relation = None
       #     selected_dataset_metadata_id = self.fields['dataset_metadata'].id
       #     if self.fields['dataset_metadata'] is not None:
       #         dataset_metadata_relation = DatasetMetadataRelation.objects.filter(dataset_metadata_id=self.fields['dataset_metadata'].id)
            # Override the product query set with a list of product excluding those already in the pricelist
            #self.fields['layer_metadata'].queryset = LayerMetadata.objects.exclude(id__in=existing)
