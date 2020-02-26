"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 28.05.19

"""
from django import forms
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _

from structure.models import User, Theme


class PasswordResetForm(forms.Form):
    email = forms.EmailField(max_length=255, required=True, label=_("E-Mail"), label_suffix="")


class PasswordChangeForm(forms.Form):
    # TODO: refactor validators... validators should be in validators.py
    password = forms.CharField(max_length=255,
                               label=_("Password"),
                               label_suffix=" ",
                               widget=forms.PasswordInput,
                               validators=[RegexValidator(
                                            regex='[a-z]',
                                            message='Password must have at least one lowercase letter',
                                            code='invalid_password'),
                                           RegexValidator(
                                               regex='[A-Z]',
                                               message='Password must have at least one Uppercase letter',
                                               code='invalid_password'),
                                           RegexValidator(
                                               regex='\d',
                                               message='Password must have at least one digit',
                                               code='invalid_password'),
                                           RegexValidator(
                                               regex='.{9}',
                                               message='Password must have at least nine characters',
                                               code='invalid_password'),
                                           ])
    password_again = forms.CharField(max_length=255, label=_("Password again"), label_suffix=" ", widget=forms.PasswordInput,)

    def clean(self):
        cleaned_data = super(PasswordChangeForm, self).clean()
        password = cleaned_data.get("password")
        password_again = cleaned_data.get("password_again")

        if password != password_again:
            self.add_error("password_again", forms.ValidationError("Password and confirmed password does not match"))

        return cleaned_data


class UserForm(forms.ModelForm):
    # TODO: refactor validators... validators should be in validators.py
    username = forms.CharField(validators=[RegexValidator(
                                           regex='.{3}',
                                           message='Username must have at least three characters',
                                           code='invalid_username'),
                                           RegexValidator(
                                           regex='[^A-Za-z0-9]',
                                           message='Special or non printable characters are not allowed',
                                           code='invalid_username',
                                           inverse_match=True),
                                           ])

    theme = forms.ModelChoiceField(queryset=Theme.objects.all(), to_field_name='name', empty_label=None,)

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