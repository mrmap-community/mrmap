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

from MrMap.forms import MrMapForm, MrMapConfirmForm, MrMapWizardForm
from MrMap.messages import SERVICE_UPDATE_WRONG_TYPE, SERVICE_ACTIVATED_TEMPLATE, SERVICE_DEACTIVATED_TEMPLATE
from MrMap.validators import validate_get_capablities_uri
from django.utils.translation import gettext_lazy as _
from django.contrib import messages

from service.helper import service_helper
from service.helper.enums import OGCServiceEnum
from service.models import Service, MrMapGroup
from service import tasks
from service.settings import NONE_UUID
from structure.models import Organization


class ServiceURIForm(forms.Form):
    uri = forms.CharField(label=_("GetRequest URI"), widget=forms.TextInput(attrs={
        "id": "capabilities-uri"
    }))


class RegisterNewResourceWizardPage1(MrMapWizardForm):
    get_request_uri = forms.URLField(
        validators=[validate_get_capablities_uri],
        label=_("Resource URL"),
        help_text=_("In case of a OGC service you may provide the GetCapabilities url.")
    )


class RegisterNewResourceWizardPage2(MrMapWizardForm):
    ogc_request = forms.CharField(label=_('OGC Request'), widget=forms.TextInput(attrs={'readonly': '', }))
    ogc_service = forms.CharField(label=_('OGC Service'), widget=forms.TextInput(attrs={'readonly': '', }))
    ogc_version = forms.CharField(label=_('OGC Version'), widget=forms.TextInput(attrs={'readonly': '', }))
    uri = forms.CharField(label=_('URI'), widget=forms.TextInput(attrs={'readonly': '', }))
    registering_with_group = forms.ModelChoiceField(
        label=_("Registration with group"),
        help_text=_("Select a group for which this resource shall be registered."),
        widget=forms.Select(attrs={'class': 'auto_submit_item'}),
        queryset=MrMapGroup.objects.none(),
        to_field_name='id',
        initial=1,
    )
    registering_for_other_organization = forms.ModelChoiceField(
        label=_("Registration for other organization"),
        help_text=_("If you need to register for another organization, select the group which has the publisher rights and select the organization in here."),
        required=False,
        queryset=Organization.objects.none(),
        to_field_name='id',
        empty_label=_("No other")
    )

    service_needs_authentication = forms.BooleanField(
        label=_("Service needs authentication"),
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'auto_submit_item', })
    )
    username = forms.CharField(label=_("Username"), required=False, disabled=True)
    password = forms.CharField(label=_("Password"), required=False, widget=forms.PasswordInput, disabled=True)
    authentication_type = forms.ChoiceField(
        label=_("Authentication type"),
        required=False,
        disabled=True,
        choices=(('http_digest', 'HTTP Digest'), ('http_basic', 'HTTP Basic'))
    )

    def __init__(self,  *args, **kwargs):
        super(RegisterNewResourceWizardPage2, self).__init__(*args, **kwargs)
        registering_with_group_key = self.prefix+"-registering_with_group" if self.prefix else "registering_with_group"
        selected_group = None
        if registering_with_group_key in self.request.POST:
            selected_group = MrMapGroup.objects.get(id=int(self.request.POST.get(registering_with_group_key)))
        service_needs_authentication_key = self.prefix+"-service_needs_authentication" if self.prefix else "service_needs_authentication"
        service_needs_authentication = None
        if service_needs_authentication_key in self.request.POST:
            service_needs_authentication = True if self.request.POST.get(service_needs_authentication_key) == 'on' else False
        elif kwargs.get("initial", {}).get("service_needs_authentication", False):
            service_needs_authentication = True

        # initial the fields if the values are transfered
        if self.requesting_user is not None:
            user_groups = self.requesting_user.get_groups({"is_public_group": False, "is_permission_group": False})
            self.fields["registering_with_group"].queryset = user_groups.all()
            self.fields["registering_with_group"].initial = user_groups.first()
        if selected_group is not None:
            self.fields["registering_for_other_organization"].queryset = selected_group.publish_for_organizations.all()
        elif self.requesting_user is not None and user_groups.first() is not None:
            self.fields[
                "registering_for_other_organization"].queryset = user_groups.first().publish_for_organizations.all()
        if service_needs_authentication:
            self.fields["service_needs_authentication"].initial = "on"
            self.fields["service_needs_authentication"].required = True
            self.fields["username"].disabled = False
            self.fields["username"].required = True
            self.fields["password"].disabled = False
            self.fields["password"].required = True
            self.fields["authentication_type"].disabled = False
            self.fields["authentication_type"].required = True


class UpdateServiceCheckForm(MrMapForm):
    url_dict = ''
    get_capabilities_uri = forms.URLField(
        validators=[validate_get_capablities_uri]
    )
    keep_custom_md = forms.BooleanField(
        label=_("Keep custom metadata"),
        initial=True,
        required=False
    )

    def __init__(self, *args, **kwargs):
        self.current_service = None if 'current_service' not in kwargs else kwargs.pop('current_service')
        self.requesting_user = None if 'requesting_user' not in kwargs else kwargs.pop('requesting_user')
        super(UpdateServiceCheckForm, self).__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super(UpdateServiceCheckForm, self).clean()

        if "get_capabilities_uri" in cleaned_data:
            uri = cleaned_data.get("get_capabilities_uri")
            self.url_dict = service_helper.split_service_uri(uri)
            new_service_type = self.url_dict.get("service")

            if self.current_service.service_type.name != new_service_type.value:
                self.add_error(None, SERVICE_UPDATE_WRONG_TYPE)

        has_update_candidate_for_service = None
        try:
            # Get service object from db
            has_update_candidate_for_service = Service.objects.get(is_update_candidate_for=self.current_service)
        except ObjectDoesNotExist:
            pass

        if has_update_candidate_for_service:
            user = has_update_candidate_for_service.created_by_user \
                if has_update_candidate_for_service.created_by_user is not None \
                else 'unknown'

            self.add_error(None,
                           _("There are still pending update requests from user '{}' for this service.").format(user))

            if self.requesting_user == user:
                self.add_error(None,
                               format_html("See your pending update request <a href={}>here.</a>",
                                           reverse_lazy('resource:pending-update',
                                                        args=(self.current_service.metadata.id,))))
                # ToDo: check if user is in group of created_by field of update_cadidate

        return cleaned_data


class UpdateOldToNewElementsForm(forms.Form):
    action_url = ''

    def __init__(self, *args, **kwargs):
        new_elements = None if 'new_elements' not in kwargs else kwargs.pop('new_elements')
        removed_elements = None if 'removed_elements' not in kwargs else kwargs.pop('removed_elements')
        choices = None if 'choices' not in kwargs else kwargs.pop('choices')
        current_service = None if 'current_service' not in kwargs else kwargs.pop('current_service')
        super(UpdateOldToNewElementsForm, self).__init__(*args, **kwargs)

        # Prepare remove elements as choices
        remove_elements_choices = [(NONE_UUID, _("---"))]
        for elem in removed_elements:
            remove_elements_choices.append((elem.metadata.id, elem.metadata.identifier))

        # Add new form fields dynamically
        for elem in new_elements:
            self.fields['new_elem_{}'.format(elem.metadata.identifier)] = forms.ChoiceField(
                label="{} ({})".format(elem.metadata.identifier, elem.metadata.title),
                choices=remove_elements_choices,
                help_text=_("Select the old layer name, if this new layer was just renamed.")
                if current_service.is_service_type(OGCServiceEnum.WMS)
                else _("Select the old featuretype name, if this new featuretype was just renamed.")
            )

        if choices is not None:
            for identifier, choice in choices.items():
                self.fields['new_elem_{}'.format(identifier)].initial = choice


class RemoveServiceForm(MrMapConfirmForm):
    def __init__(self, instance, *args, **kwargs):
        self.instance = instance
        super(RemoveServiceForm, self).__init__(*args, **kwargs)

    def process_remove_service(self):
        service_helper.remove_service(self.instance, self.requesting_user)


class ActivateServiceForm(MrMapConfirmForm):
    def __init__(self, instance, *args, **kwargs):
        self.instance = instance
        super(ActivateServiceForm, self).__init__(*args, **kwargs)

    def process_activate_service(self):
        self.instance.is_active = not self.instance.is_active
        self.instance.save()

        # run activation async!
        tasks.async_activate_service.delay(self.instance.id, self.requesting_user.id, self.instance.is_active)

        # If metadata WAS active, then it will be deactivated now
        if self.instance.is_active:
            msg = SERVICE_ACTIVATED_TEMPLATE.format(self.instance.title)
        else:
            msg = SERVICE_DEACTIVATED_TEMPLATE.format(self.instance.title)
        messages.success(self.request, msg)
