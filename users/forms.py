"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 28.05.19

"""
from django import forms
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _

from MapSkinner.validators import PASSWORD_VALIDATORS, USERNAME_VALIDATORS
from structure.models import User, Theme


class PasswordResetForm(forms.Form):
    email = forms.EmailField(max_length=255, required=True, label=_("E-Mail"), label_suffix="")


class PasswordChangeForm(forms.Form):
    password = forms.CharField(min_length=9,
                               max_length=255,
                               label=_("Password"),
                               label_suffix=" ",
                               widget=forms.PasswordInput,
                               validators=PASSWORD_VALIDATORS)
    password_again = forms.CharField(max_length=255, label=_("Password again"), label_suffix=" ", widget=forms.PasswordInput,)

    def clean(self):
        cleaned_data = super(PasswordChangeForm, self).clean()
        password = cleaned_data.get("password")
        password_again = cleaned_data.get("password_again")

        if password != password_again:
            self.add_error("password_again", forms.ValidationError(_("Password and confirmed password does not match")))

        return cleaned_data


class UserForm(forms.ModelForm):
    username = forms.CharField(min_length=5,
                               max_length=255,
                               validators=USERNAME_VALIDATORS)
    theme = forms.ModelChoiceField(queryset=Theme.objects.all(), to_field_name='name', empty_label=None, required=False)

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