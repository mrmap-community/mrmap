"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 09.07.19

"""
from django.forms import ModelForm, TextInput
from django.utils.translation import gettext_lazy as _

from service.models import Metadata


class MetadataEditorForm(ModelForm):
    action_url = None

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
        widgets = {
            "categories": TextInput(),
            "keywords": TextInput(),
        }

    def __init__(self, *args, **kwargs):
        # first call parent's constructor
        super(MetadataEditorForm, self).__init__(*args, **kwargs)

        # there's a `fields` property now
        self.fields['terms_of_use'].required = False
        if kwargs.get("instance", None) is not None:
            self.initial["keywords"] = ",".join([k.keyword for k in self.instance.keywords.all()])



class FeatureTypeEditorForm(ModelForm):
    class Meta:
        model = Metadata
        fields = [
            "title",
            "abstract",
        ]