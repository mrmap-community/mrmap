import os

from captcha.fields import CaptchaField
from dal import autocomplete
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.db.models import Q
from django.forms import ModelForm, MultipleHiddenInput
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from MrMap.forms import MrMapConfirmForm
from MrMap.messages import ORGANIZATION_IS_OTHERS_PROPERTY
from django.contrib import messages


class RemoveOrganizationForm(MrMapConfirmForm):
    def __init__(self, instance=None, *args, **kwargs):
        self.instance = instance
        super(RemoveOrganizationForm, self).__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super(RemoveOrganizationForm, self).clean()

        if self.instance.created_by != self.requesting_user:
            self.add_error(None, ORGANIZATION_IS_OTHERS_PROPERTY)

        if not cleaned_data.get('is_confirmed'):
            self.add_error('is_confirmed', _('You have to confirm the checkbox.'))

        return cleaned_data

    def process_remove_org(self):
        org_name = self.instance.organization_name
        self.instance.delete()
        messages.success(self.request, message=_('Organization {} successfully deleted.'.format(org_name)))


class RegistrationForm(UserCreationForm):

    email = forms.EmailField(required=True)

    dsgvo = forms.BooleanField(
        initial=False,
        label=_("I understand and accept that my data will be automatically processed and securely stored, as it is stated in the general data protection regulation (GDPR)."),
        required=True
    )
    captcha = CaptchaField(label=_("I'm not a robot"), required=True)

    class Meta:
        model = get_user_model()
        fields = ('username',
                  'password1',
                  'password2',
                  'first_name',
                  'last_name',
                  'email',
                  'confirmed_newsletter',
                  'confirmed_survey',
                  'dsgvo',
                  'captcha')

    def clean(self):
        cleaned_data = super(RegistrationForm, self).clean()

        # Username taken check
        u_name = cleaned_data.get("username", None)
        u_exists = get_user_model().objects.filter(username=u_name).exists()
        if u_exists:
            self.add_error("username", forms.ValidationError(_("Username is already taken. Try another.")))
        return cleaned_data

    def save(self, commit=True):
        self.instance.person_name = self.instance.first_name + " " + self.instance.last_name
        self.instance.is_active = False
        return super().save(commit=commit)
