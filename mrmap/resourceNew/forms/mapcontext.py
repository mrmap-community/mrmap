from django import forms
from django.utils.translation import gettext_lazy as _

from MrMap.widgets import BootstrapDatePickerInput
from main.forms import ModelForm
from resourceNew.models.mapcontext import MapContext


class MapContextForm(ModelForm):
    # layer = MetadataModelChoiceField(
    #     queryset=Metadata.objects.none(),
    #     widget=autocomplete.ModelSelect2(
    #         url='editor:layer-autocomplete',
    #     ),
    #     required=False, )
    # layer_tree = forms.CharField(widget=forms.HiddenInput)

    abstract = forms.CharField(label=_('Abstract'), help_text=_("brief summary of the topic of this map context"))

    class Meta:
        model = MapContext
        fields = ('title', 'abstract')
        widgets = {
            'update_date': BootstrapDatePickerInput(),
            'layer_tree': forms.HiddenInput()
        }


class MapContextLayerForm(forms.Form):
    id = forms.CharField(widget=forms.HiddenInput)
    parent = forms.CharField(widget=forms.HiddenInput, required=False)
    title = forms.CharField(widget=forms.TextInput, required=False)
