"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 28.05.19

"""
from django import forms
from django.contrib.auth import get_user_model
from django.forms import HiddenInput
from users.models.users import Subscription
from extras.forms import ModelForm
from captcha.fields import CaptchaField
from django.contrib.auth.forms import UserCreationForm
from django.utils.translation import gettext_lazy as _


class MrMapUserForm(ModelForm):
    class Meta:
        model = get_user_model()
        fields = [
            "first_name",
            "last_name",
            "email",
            "confirmed_newsletter",
            "confirmed_survey",
            # FIXME: this shall only be visible for administrator...
            "groups"
        ]


class SubscriptionForm(ModelForm):
    class Meta:
        model = Subscription
        fields = ('service', 'user', 'notify_on_update', 'notify_on_metadata_edit', 'notify_on_access_edit')
        widgets = {
            'user': HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if kwargs.get('instance', None):
            # it' a update of an existing subscription. For that we set the metadata field to readonly.
            self.fields['metadata'].widget = HiddenInput()


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
