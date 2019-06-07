"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 28.05.19

"""
from django import forms
from django.utils.translation import gettext_lazy as _

from structure.models import User


class PasswordResetForm(forms.Form):
    email = forms.EmailField(max_length=255, required=True, label=_("E-Mail"), label_suffix="")


class PasswordChangeForm(forms.Form):
    password = forms.CharField(max_length=255, label=_("Password"), label_suffix=" ", widget=forms.PasswordInput)
    password_again = forms.CharField(max_length=255, label=_("Password again"), label_suffix=" ", widget=forms.PasswordInput)


class UserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = '__all__'
        field_order = [
            'username',
            'person_name',
        ]
        exclude = [
            'logged_in',
            'salt',
            'last_login',
            'created_on',
            'groups',
            'organization',
            'organization',
            'confirmed_dsgvo',
            'is_active',
            'password',
            'address_type',
        ]