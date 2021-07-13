from django import forms
from main.forms import ModelForm
from MrMap.widgets import BootstrapDatePickerInput
from resourceNew.models.mapcontext import MapContext


class MapContextForm(ModelForm):
    # layer = MetadataModelChoiceField(
    #     queryset=Metadata.objects.none(),
    #     widget=autocomplete.ModelSelect2(
    #         url='editor:layer-autocomplete',
    #     ),
    #     required=False, )
    # layer_tree = forms.CharField(widget=forms.HiddenInput)

    class Meta:
        model = MapContext
        fields = ('title', 'abstract')
        widgets = {
            'update_date': BootstrapDatePickerInput(),
            'layer_tree': forms.HiddenInput()
        }
