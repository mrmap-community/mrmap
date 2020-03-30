from captcha.fields import CaptchaField
from django import forms
from django.forms import ModelForm
from django.utils.translation import gettext_lazy as _

from MapSkinner.settings import MIN_PASSWORD_LENGTH, MIN_USERNAME_LENGTH
from MapSkinner.validators import PASSWORD_VALIDATORS, USERNAME_VALIDATORS
from structure.models import MrMapGroup, Organization


class LoginForm(forms.Form):
    username = forms.CharField(max_length=255, label=_("Username"), label_suffix=" ")
    password = forms.CharField(max_length=255, label=_("Password"), label_suffix=" ", widget=forms.PasswordInput)
    next = forms.CharField(max_length=255, show_hidden_initial=False, widget=forms.HiddenInput(), required=False)


class GroupForm(ModelForm):
    # this action_url must fill after this object is created,
    # cause the action_url containing the id of the group, which is not present on building time;
    # maybe we could fill it by the constructor
    action_url = ''

    description = forms.CharField(
        widget=forms.Textarea(),
        required=False,
    )

    class Meta:
        model = MrMapGroup
        fields = [
            "name",
            "description",
            "role",
            "parent_group"
        ]

class PublisherForOrganizationForm(forms.Form):
    action_url = ''
    organization_name = forms.CharField(max_length=500, label_suffix=" ", label=_("Organization"), disabled=True)
    group = forms.ChoiceField(widget=forms.Select)
    request_msg = forms.CharField(
        widget=forms.Textarea(),
        required=True,
        label=_("Message"),
        label_suffix=" ",
    )


class OrganizationForm(ModelForm):
    # this action_url must fill after this object is created,
    # cause the action_url containing the id of the group, which is not present on building time;
    # maybe we could fill it by the constructor
    action_url = ''

    description = forms.CharField(
        widget=forms.Textarea(),
        required=False,
    )
    person_name = forms.CharField(label=_("Contact person"), required=True)

    field_order = ["organization_name", "description", "parent"]

    class Meta:
        model = Organization
        fields = '__all__'
        exclude = ["created_by", "address_type", "is_auto_generated"]


class RemoveGroupForm(forms.Form):
    action_url = ''
    is_confirmed = forms.BooleanField(label=_('Do you really want to remove this group?'))


class RemoveOrganizationForm(forms.Form):
    action_url = ''
    is_confirmed = forms.BooleanField(label=_('Do you really want to remove this organization?'))


class RegistrationForm(forms.Form):
    username = forms.CharField(
        min_length=MIN_USERNAME_LENGTH,
        max_length=255,
        validators=USERNAME_VALIDATORS,
        label=_("Username"),
        label_suffix=" ",
        required=True
    )
    password = forms.CharField(
        min_length=MIN_PASSWORD_LENGTH,
        max_length=255,
        label=_("Password"),
        label_suffix=" ",
        widget=forms.PasswordInput,
        required=True,
        validators=PASSWORD_VALIDATORS
    )

    password_check = forms.CharField(
        max_length=255,
        label=_("Password again"),
        label_suffix=" ",
        widget=forms.PasswordInput,
        required=True
    )

    first_name = forms.CharField(max_length=200, label=_("First name"), label_suffix=" ", required=True)
    last_name = forms.CharField(max_length=200, label=_("Last name"), label_suffix=" ", required=True)
    email = forms.EmailField(max_length=100, label=_("E-mail address"), label_suffix=" ", required=True)
    address = forms.CharField(max_length=100, label=_("Address"), label_suffix=" ", required=False)
    postal_code = forms.CharField(max_length=100, label=_("Postal code"), label_suffix=" ", required=False)
    city = forms.CharField(max_length=100, label=_("City"), label_suffix=" ", required=False)
    phone = forms.CharField(max_length=100, label=_("Phone"), label_suffix=" ", required=True)
    facsimile = forms.CharField(max_length=100, label=_("Facsimile"), label_suffix=" ", required=False)
    newsletter = forms.BooleanField(label=_("I want to sign up for the newsletter"), required=False, initial=True)
    survey = forms.BooleanField(label=_("I want to participate in surveys"), required=False, initial=True)
    dsgvo = forms.BooleanField(
        initial=False,
        label=_("I understand and accept that my data will be automatically processed and securely stored, as it is stated in the general data protection regulation (GDPR)."),
        required=True
    )
    captcha = CaptchaField(label=_("I'm not a robot"), required=True)

    def clean(self):
        cleaned_data = super(RegistrationForm, self).clean()
        password = cleaned_data.get("password")
        password_check = cleaned_data.get("password_check")

        if password != password_check:
            self.add_error("password_check", forms.ValidationError(_("Password and confirmed password does not match")))

        return cleaned_data
