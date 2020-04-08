"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 08.04.20

"""
from django import forms
from rest_framework.authtoken.models import Token


class TokenForm(forms.ModelForm):
    action_url = None

    class Meta:
        model = Token
        exclude = [
            'user',
        ]
        widgets = {
            "key": forms.TextInput(
                attrs={
                    "readonly": "readonly",
                }
            )
        }

    def __init__(self, *args, **kwargs):
        # first call parent's constructor
        super(TokenForm, self).__init__(*args, **kwargs)
        self.fields["key"].required = False
