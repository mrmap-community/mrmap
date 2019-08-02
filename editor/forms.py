"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 09.07.19

"""
from django.forms import ModelForm, Select, SelectMultiple

from service.models import Metadata, FeatureType


class MetadataEditorForm(ModelForm):
    class Meta:
        model = Metadata
        fields = [
            "title",
            "abstract",
            "access_constraints",
            "terms_of_use",
            # "metadata_url",
            # "keywords",
            # "categories",
            # "reference_system",
        ]
        labels = {
            # "metadata_url": "ISO metadata URL",
        }

class FeatureTypeEditorForm(ModelForm):
    class Meta:
        model = FeatureType
        fields = [
            "title",
            "abstract",
        ]