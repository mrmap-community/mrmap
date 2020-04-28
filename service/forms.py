"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 15.04.19

"""
from django import forms
from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse_lazy
from django.utils.html import format_html

from MapSkinner.consts import SERVICE_ADD
from MapSkinner.messages import SERVICE_UPDATE_WRONG_TYPE
from MapSkinner.validators import validate_get_request_uri
from django.utils.translation import gettext_lazy as _

from service.helper import service_helper
from service.models import Service, Document


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
        if user is not None:
            user_groups = user.get_groups()
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


class RemoveServiceForm(forms.Form):
    action_url = ''
    is_confirmed = forms.BooleanField(label=_('Do you really want to remove this service?'))


class UpdateServiceCheckForm(forms.Form):
    action_url = ''
    url_dict = ''
    get_capabilities_uri = forms.URLField(
        validators=[validate_get_request_uri]
    )
    keep_custom_md = forms.BooleanField(
        label=_("Keep custom metadata"),
        initial=True,
        required=False
    )

    def __init__(self, *args, **kwargs):
        self.current_service = None if 'current_service' not in kwargs else kwargs.pop('current_service')
        self.current_document = None if 'current_document' not in kwargs else kwargs.pop('current_document')
        self.requesting_user = None if 'requesting_user' not in kwargs else kwargs.pop('requesting_user')
        super(UpdateServiceCheckForm, self).__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super(UpdateServiceCheckForm, self).clean()

        if "get_capabilities_uri" in cleaned_data:
            uri = cleaned_data.get("get_capabilities_uri")
            self.url_dict = service_helper.split_service_uri(uri)
            new_service_type = self.url_dict.get("service")

            if self.current_service.servicetype.name != new_service_type.value:
                self.add_error(None, SERVICE_UPDATE_WRONG_TYPE)

        has_update_candidate_for_service = None
        has_update_candidate_for_document = None
        try:
            # Get service object from db
            has_update_candidate_for_service = Service.objects.get(is_update_candidate_for=self.current_service)
            has_update_candidate_for_document = Document.objects.get(is_update_candidate_for=self.current_document)
        except ObjectDoesNotExist:
            pass

        if has_update_candidate_for_service or has_update_candidate_for_document:
            user = has_update_candidate_for_service.created_by_user \
                if has_update_candidate_for_service.created_by_user is not None \
                else 'unknown'

            self.add_error(None,
                           _("There are still pending update requests from user '{}' for this service.").format(user))

            if self.requesting_user == user:
                self.add_error(None,
                               format_html("See your pending update request <a href={}>here.</a>",
                                           reverse_lazy('service:pending-update',
                                                        args=(self.current_service.metadata.id,))))
                # ToDo: check if user is in group of created_by field of update_cadidate

        return cleaned_data


class UpdateOldToNewElementsForm(forms.Form):
    action_url = ''

    def __init__(self, *args, **kwargs):
        new_elements = None if 'new_elements' not in kwargs else kwargs.pop('new_elements')
        removed_elements = None if 'removed_elements' not in kwargs else kwargs.pop('removed_elements')
        choices = None if 'choices' not in kwargs else kwargs.pop('choices')
        super(UpdateOldToNewElementsForm, self).__init__(*args, **kwargs)

        # Prepare remove elements as choices
        remove_elements_choices = [(-1, _("---"))]
        for elem in removed_elements:
            remove_elements_choices.append((elem.metadata.id, elem.metadata.identifier))

        # Add new form fields dynamically
        for elem in new_elements:
            self.fields['new_elem_{}'.format(elem.metadata.identifier)] = forms.ChoiceField(
                label="{} ({})".format(elem.metadata.identifier, elem.metadata.title),
                choices=remove_elements_choices,
                help_text=_("Select the old layer name, if this new layer was just renamed.")
            )

        if choices is not None:
            for identifier, choice in choices.items():
                self.fields['new_elem_{}'.format(identifier)].initial = choice
