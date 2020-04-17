"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 09.07.19

"""
from dal import autocomplete
from django.forms import ModelForm, TextInput, CharField, CheckboxSelectMultiple, ModelChoiceField
from django.utils.translation import gettext_lazy as _

from service.models import Metadata, Keyword


class MetadataEditorForm(ModelForm):
    action_url = None

    def __init__(self, *args, **kwargs):
        # first call parent's constructor
        super(MetadataEditorForm, self).__init__(*args, **kwargs)

        # there's a `fields` property now
        self.fields['terms_of_use'].required = False
        self.fields['categories'].required = False
        self.fields['keywords'].required = False

    class Meta:
        model = Metadata
        fields = [
            "title",
            "abstract",
            "access_constraints",
            "terms_of_use",
            "keywords",
            "categories",
        ]
        help_texts = {
            "title": _("Edit the title."),
            "abstract": _("Edit the description. Keep it short and simple."),
            "access_constraints": _("Edit the access constraints."),
            "terms_of_use": _("Select another licence."),
            "keywords": _(""),  # Since keywords are handled differently, this can be empty
            "categories": _("Select categories for this resource."),
        }
        widgets = {
            "categories": autocomplete.ModelSelect2Multiple(
                url='editor:category-autocomplete',
                attrs={
                    "data-containercss": {
                        "height": "3em",
                        "width": "3em",
                    },
                },
            ),
            'keywords': autocomplete.ModelSelect2Multiple(
                url='editor:keyword-autocomplete',
                attrs={
                    "data-containerCss": {
                        "height": "3em",
                        "width": "3em",
                    }
                },
            ),
        }

class FeatureTypeEditorForm(ModelForm):
    class Meta:
        model = Metadata
        fields = [
            "title",
            "abstract",
        ]