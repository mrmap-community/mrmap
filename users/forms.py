"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 28.05.19

"""
from django import forms


class PasswordResetForm(forms.Form):
    email = forms.CharField(max_length=255, required=True)
