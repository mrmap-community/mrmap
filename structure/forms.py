from captcha.fields import CaptchaField
from django import forms
from django.forms import ModelForm
from django.utils.translation import gettext_lazy as _

from structure.models import Group, Organization


class LoginForm(forms.Form):
    username = forms.CharField(max_length=255, label=_("Username"), label_suffix=" ")
    password = forms.CharField(max_length=255, label=_("Password"), label_suffix=" ", widget=forms.PasswordInput)


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
        model = Group
        fields = '__all__'
        exclude = [
            "created_by",
            "publish_for_organizations",
            "role"
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
    is_confirmed = forms.BooleanField(label='Do you really want to remove this group?')


class RemoveOrganizationForm(forms.Form):
    action_url = ''
    is_confirmed = forms.BooleanField(label='Do you really want to remove this organization?')


class RegistrationForm(forms.Form):
    # TODO: implement validators for this fields; see UserForm in users/forms.py
    username = forms.CharField(max_length=255, label=_("Username"), label_suffix=" ", required=True)
    password = forms.CharField(max_length=255, label=_("Password"), label_suffix=" ", widget=forms.PasswordInput, required=True)
    password_check = forms.CharField(max_length=255, label=_("Password again"), label_suffix=" ", widget=forms.PasswordInput, required=True)

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
    dsgvo = forms.BooleanField(initial=False, label=_("I understand and accept that my data will be automatically processed and securely stored, as it is stated in the general data protection regulation (GDPR)."), required=True)
    captcha = CaptchaField(label=_("I'm not a robot"), required=True)
