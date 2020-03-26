"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 15.04.19

"""
from django import forms

from MapSkinner.validators import validate_get_request_uri
from django.utils.translation import gettext_lazy as _


class ServiceURIForm(forms.Form):
    uri = forms.CharField(label=_("GetRequest URI"), widget=forms.TextInput(attrs={
        "id": "capabilities-uri"
    }))


class RegisterNewServiceWizardPage1(forms.Form):
    page = forms.IntegerField(widget=forms.HiddenInput(), initial=1)
    get_request_uri = forms.URLField(validators=[validate_get_request_uri])


class RegisterNewServiceWizardPage2(forms.Form):
    page = forms.IntegerField(required=False, widget=forms.HiddenInput(), initial=2)
    is_form_update = forms.BooleanField(required=False, widget=forms.HiddenInput(), initial=False)
    ogc_request = forms.CharField(label='OGC Request', widget=forms.TextInput(attrs={'readonly': '', }))
    ogc_service = forms.CharField(label='OGC Service', widget=forms.TextInput(attrs={'readonly': '', }))
    ogc_version = forms.CharField(label='OGC Version', widget=forms.TextInput(attrs={'readonly': '', }))
    uri = forms.CharField(label='URI', widget=forms.TextInput(attrs={'readonly': '', }))
    registering_with_group = forms.ModelChoiceField(widget=forms.Select(attrs={'class': 'auto_submit_item'}), queryset=None, to_field_name='id', initial=1)
    registering_for_other_organization = forms.ModelChoiceField(required=False, queryset=None, to_field_name='id', empty_label="No other")

    service_needs_authentication = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={'class': 'auto_submit_item', }))
    username = forms.CharField(required=False, disabled=True)
    password = forms.CharField(required=False, widget=forms.PasswordInput, disabled=True)
    authentication_type = forms.ChoiceField(required=False, disabled=True, choices=(('http_digest', 'HTTP Digest'), ('http_basic', 'HTTP Basic')))

    def __init__(self, *args, **kwargs):
        # pop custom kwargs before invoke super constructor and hold them
        self.user = kwargs.pop('user')
        self.selected_group = kwargs.pop('selected_group')
        self.service_needs_authentication = kwargs.pop('service_needs_authentication')

        # run super constructor to construct the form
        super(RegisterNewServiceWizardPage2, self).__init__(*args, **kwargs)

        # initial the fields with the poped kwargs
        user_groups = self.user.get_groups()
        self.fields['registering_with_group'].queryset = user_groups
        self.fields['registering_with_group'].initial = user_groups.first()
        self.fields['registering_for_other_organization'].queryset = self.selected_group.publish_for_organizations.all()
        self.fields['service_needs_authentication'].initial = self.service_needs_authentication

        if self.service_needs_authentication == 'on':
            self.fields['username'].disabled = False
            self.fields['username'].required = True
            self.fields['password'].disabled = False
            self.fields['password'].required = True
            self.fields['authentication_type'].disabled = False
            self.fields['authentication_type'].required = True


class RegisterNewServiceWizardPage3(forms.Form):
    page = forms.IntegerField(widget=forms.HiddenInput(), initial=3)
    get_request_uri = forms.CharField()


class RemoveService(forms.Form):
    action_url = ''
    is_confirmed = forms.BooleanField(label=_('Do you really want to remove this service?'))
