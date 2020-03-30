"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 15.04.19

"""
from django import forms
from django.urls import reverse_lazy

from MapSkinner.consts import SERVICE_ADD
from MapSkinner.validators import validate_get_request_uri
from django.utils.translation import gettext_lazy as _


class ServiceURIForm(forms.Form):
    uri = forms.CharField(label=_("GetRequest URI"), widget=forms.TextInput(attrs={
        "id": "capabilities-uri"
    }))


class RegisterNewServiceWizardPage1(forms.Form):
    action_url = reverse_lazy(SERVICE_ADD,)
    page = forms.IntegerField(widget=forms.HiddenInput(), initial=1)
    get_request_uri = forms.URLField(validators=[validate_get_request_uri])


class RegisterNewServiceWizardPage2(forms.Form):
    action_url = reverse_lazy(SERVICE_ADD,)
    page = forms.IntegerField(required=False, widget=forms.HiddenInput(), initial=2)
    is_form_update = forms.BooleanField(required=False, widget=forms.HiddenInput(), initial=False)
    ogc_request = forms.CharField(label=_('OGC Request'), widget=forms.TextInput(attrs={'readonly': '', }))
    ogc_service = forms.CharField(label=_('OGC Service'), widget=forms.TextInput(attrs={'readonly': '', }))
    ogc_version = forms.CharField(label=_('OGC Version'), widget=forms.TextInput(attrs={'readonly': '', }))
    uri = forms.CharField(label=_('URI'), widget=forms.TextInput(attrs={'readonly': '', }))
    registering_with_group = forms.ModelChoiceField(label=_("Registration with group"), widget=forms.Select(attrs={'class': 'auto_submit_item'}), queryset=None, to_field_name='id', initial=1)
    registering_for_other_organization = forms.ModelChoiceField(label=_("Registration for other organization"), required=False, queryset=None, to_field_name='id', empty_label=_("No other"))

    service_needs_authentication = forms.BooleanField(label=_("Service needs authentication"), required=False, widget=forms.CheckboxInput(attrs={'class': 'auto_submit_item', }))
    username = forms.CharField(label=_("Username"), required=False, disabled=True)
    password = forms.CharField(label=_("Password"), required=False, widget=forms.PasswordInput, disabled=True)
    authentication_type = forms.ChoiceField(label=_("Authentication type"), required=False, disabled=True, choices=(('http_digest', 'HTTP Digest'), ('http_basic', 'HTTP Basic')))

    def __init__(self, *args, **kwargs):
        # pop custom kwargs before invoke super constructor and hold them
        user = None if 'user' not in kwargs else kwargs.pop('user')
        selected_group = None if 'selected_group' not in kwargs else kwargs.pop('selected_group')
        service_needs_authentication = False if 'service_needs_authentication' not in kwargs else kwargs.pop('service_needs_authentication')

        # run super constructor to construct the form
        super(RegisterNewServiceWizardPage2, self).__init__(*args, **kwargs)
        # initial the fields if the values are transfered
        user_groups = user.get_groups()
        if user is not None:
            self.fields["registering_with_group"].queryset = user_groups.all()
            self.fields["registering_with_group"].initial = user_groups.first()
        if selected_group is not None:
            self.fields["registering_for_other_organization"].queryset = selected_group.publish_for_organizations.all()
        elif user is not None and user_groups.first() is not None:
            self.fields["registering_for_other_organization"].queryset = user_groups.first().publish_for_organizations.all()
        if service_needs_authentication:
            self.fields["service_needs_authentication"].initial = "on"
            self.fields["service_needs_authentication"].required = True
            self.fields["username"].disabled = False
            self.fields["username"].required = True
            self.fields["password"].disabled = False
            self.fields["password"].required = True
            self.fields["authentication_type"].disabled = False
            self.fields["authentication_type"].required = True


class RemoveService(forms.Form):
    action_url = ''
    is_confirmed = forms.BooleanField(label=_('Do you really want to remove this service?'))
