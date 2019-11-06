"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 09.07.19

"""
from django.forms import ModelForm, CheckboxInput, SelectMultiple
from django.utils.translation import gettext_lazy as _

from service.models import Metadata, FeatureType


class MetadataEditorForm(ModelForm):
    class Meta:
        model = Metadata
        fields = [
            "title",
            "abstract",
            "access_constraints",
            "terms_of_use",
            "inherit_proxy_uris",
            "is_secured",
            "can_be_called_by",
            "can_be_queried_by",
            # "metadata_url",
            # "keywords",
            # "categories",
            # "reference_system",
        ]
        labels = {
            "inherit_proxy_uris": _("Use metadata proxy"),
            "can_be_queried_by": _("Can be queried by group"),
            "can_be_called_by": _("Can be called by group"),
        }
        widgets = {
            "inherit_proxy_uris": CheckboxInput(attrs={"class": "checkbox-input"}),
            "is_secured": CheckboxInput(attrs={"class": "checkbox-input"}),
            "can_be_queried_by": SelectMultiple(attrs={"class": "secured-selector"}),
            "can_be_called_by": SelectMultiple(attrs={"class": "secured-selector"}),
        }


class FeatureTypeEditorForm(ModelForm):
    class Meta:
        model = Metadata
        fields = [
            "title",
            "abstract",
        ]