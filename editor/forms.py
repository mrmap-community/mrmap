"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 09.07.19

"""
from django.forms import ModelForm, CheckboxInput, CheckboxSelectMultiple
from django.utils.translation import gettext_lazy as _
from django import forms

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
            "use_proxy_uri",
            "categories",
            "keywords",
        ]
        labels = {
            "use_proxy_uri": _("Use proxy"),
        }
        widgets = {
            "use_proxy_uri": CheckboxInput(),
            "categories": CheckboxSelectMultiple(),
            "keywords": CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        # first call parent's constructor
        super(MetadataEditorForm, self).__init__(*args, **kwargs)

        # there's a `fields` property now
        self.fields['terms_of_use'].required = False
        self.fields['categories'].required = False
        self.fields['keywords'].required = False


class FeatureTypeEditorForm(ModelForm):
    class Meta:
        model = Metadata
        fields = [
            "title",
            "abstract",
        ]