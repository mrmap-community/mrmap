"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 09.07.19

"""
from django.forms import ModelForm, CheckboxInput
from django.utils.translation import gettext_lazy as _

from service.models import Metadata


class MetadataEditorForm(ModelForm):
    class Meta:
        model = Metadata
        fields = [
            "title",
            "abstract",
            "access_constraints",
            "terms_of_use",
            "use_proxy_uri",
            # "metadata_url",
            # "keywords",
            # "categories",
            # "reference_system",
        ]
        labels = {
            "use_proxy_uri": _("Use proxy"),
        }
        widgets = {
            "use_proxy_uri": CheckboxInput(attrs={"class": "checkbox-input"}),
        }


class FeatureTypeEditorForm(ModelForm):
    class Meta:
        model = Metadata
        fields = [
            "title",
            "abstract",
        ]