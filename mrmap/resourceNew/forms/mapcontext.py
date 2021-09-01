from django import forms
from django.forms import TextInput
from django.utils.translation import gettext_lazy as _

from main.forms import ModelForm
from resourceNew.models.mapcontext import MapContext, MapContextLayer


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


class MapContextLayerForm(ModelForm):
    #parent_form_idx = forms.CharField(max_length=20, required=False)

    class Meta:
        model = MapContextLayer
        # widgets = {
        #     'id': TextInput(),
        #     'parent': TextInput()
        # }
        # fields = ['id', 'parent', 'parent_form_idx', 'name']
        fields = '__all__'
