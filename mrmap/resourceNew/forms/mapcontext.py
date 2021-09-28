from dal import autocomplete
from django import forms
from django.forms import ModelForm, HiddenInput
from django.utils.translation import gettext_lazy as _

from resourceNew.models import Layer, DatasetMetadataRelation
from resourceNew.models.mapcontext import MapContext, MapContextLayer


class MapContextForm(ModelForm):
    abstract = forms.CharField(label=_('Abstract'), help_text=_("brief summary of the topic of this map context"))

    class Meta:
        model = MapContext
        fields = ('title', 'abstract')


class MapContextLayerForm(ModelForm):
    parent_form_idx = forms.CharField(required=False, widget=HiddenInput)

    def __init__(self, *args, **kargs):
        super().__init__(*args, **kargs)
        self.fields['layer'].queryset = Layer.objects.none()
        if 'dataset_metadata' in self.data:
            try:
                dataset_metadata_id = int(self.data.get('dataset_metadata'))
                dataset_metadata_relation = DatasetMetadataRelation.objects.filter(
                    dataset_metadata_id=dataset_metadata_id)
                if len(dataset_metadata_relation) > 0:
                    layers = Layer.objects.filter(id__in=dataset_metadata_relation.values('layer'))
                else:
                    layers = Layer.objects.none()
                self.fields['layer'].queryset = layers
            except (ValueError, TypeError):
                pass  # invalid input from the client; ignore and fallback to empty City queryset
        elif self.instance.pk:
            dataset_metadata_relation = DatasetMetadataRelation.objects.filter(
                dataset_metadata_id=self.instance.dataset_metadata)
            self.fields['layer'].queryset = Layer.objects.filter(id__in=dataset_metadata_relation.values('layer'))

    class Meta:
        model = MapContextLayer
        widgets = {
            'parent': HiddenInput(),
            # TODO: add autocomplete Widget to dataset_metadata

        }
        fields = [
            'id',
            'parent',
            'parent_form_idx',
            'name',
            'title',
            'dataset_metadata',
            'layer',
            'preview_image'
        ]
