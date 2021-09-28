from django import forms
from django.forms import ModelForm, HiddenInput
from django.utils.translation import gettext_lazy as _

from registry.models.mapcontext import MapContext, MapContextLayer


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
            'parent': HiddenInput()
        }
        fields = ['id', 'parent', 'parent_form_idx', 'name', 'title']
