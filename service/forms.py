"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 15.04.19

"""
from django import forms
from django.utils.translation import gettext_lazy as _


class NewServiceURIForm(forms.Form):
    uri = forms.CharField(label=_("GetRequest URI"), widget=forms.TextInput(attrs={
        "id": "capabilities-uri"
    }))
