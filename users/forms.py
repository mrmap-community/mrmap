"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 28.05.19

"""
from dal import autocomplete
from django import forms
from django.forms import HiddenInput
from django.http import HttpRequest
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from MrMap.forms import MrMapModelForm
from MrMap.messages import ACCOUNT_UPDATE_SUCCESS
from service.helper.enums import MetadataEnum, MetadataRelationEnum
from service.models import Metadata
from structure.models import MrMapUser
from users.models import Subscription


class MrMapUserForm(forms.ModelForm):
    class Meta:
        model = MrMapUser
        fields = [
            "first_name",
            "last_name",
            "email",
            "confirmed_newsletter",
            "confirmed_survey",
            "theme",
            "groups"
        ]
        widgets = {
            'groups': autocomplete.ModelSelect2Multiple(
                url='editor:groups',
            )
        }

    def process_account_change(self):
        # save changes
        user = self.save()
        user.save()
        messages.add_message(self.request, messages.SUCCESS, ACCOUNT_UPDATE_SUCCESS)


class SubscriptionForm(MrMapModelForm):
    not_harvested_trough = ~Q(related_metadatas__to_metadatas__relation_type=MetadataRelationEnum.HARVESTED_THROUGH.value) |\
                           ~Q(related_metadatas__from_metadatas__relation_type=MetadataRelationEnum.HARVESTED_THROUGH.value)

    metadata = forms.ModelChoiceField(
        label=_("Service"),
        help_text=_("Select the service you want to subscribe. When you edit an existing subscription, you can not change this selection."),
        queryset=Metadata.objects.filter(
            Q(metadata_type=MetadataEnum.SERVICE.value, is_active=True) & not_harvested_trough
        ),
        widget=autocomplete.ModelSelect2(
            url='editor:service-autocomplete',
        ),
    )

    class Meta:
        model = Subscription
        fields = [
            "metadata",
            "notify_on_update",
            "notify_on_metadata_edit",
            "notify_on_access_edit",
        ]
        help_texts = {
            "notify_on_update": _("Sends an e-mai if the service has been updated."),
            "notify_on_access_edit": _("Sends an e-mai if the service's access has been changed."),
            "notify_on_metadata_edit": _("Sends an e-mai if the service's metadata has been changed."),
        }

    def __init__(self, request: HttpRequest, *args, **kwargs):
        self.request = request
        super().__init__(*args, **kwargs)
        # don't touch this. User shall not be able to append groups here. For that, the request system is recommended.
        self.fields['groups'].queryset = self.request.user.get_groups

    def clean(self):
        cleaned_data = super().clean()
        committed_groups = cleaned_data.get('groups')
        current_groups = self.request.user.get_groups

        # cause the queryset limits the user in only leave groups, we only need to iterate over the diff.
        # the diff contains all groups the user want to leave
        diff = current_groups.difference(committed_groups)
        for group in diff:
            if group.user_set.count() <= 1:
                self.add_error('groups', _(f'You can\'t leave {group}, cause you are the last member of it.'))
        return cleaned_data

    def save(self, commit=True):
        return self.instance


class SubscriptionForm(forms.ModelForm):
    class Meta:
        model = Subscription
        fields = ('metadata', 'user', 'notify_on_update', 'notify_on_metadata_edit', 'notify_on_access_edit')
        widgets = {
            'metadata': autocomplete.ModelSelect2(
                            url='editor:service-autocomplete',

                        ),
            'user': HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if kwargs.get('instance', None):
            # it' a update of an existing subscription. For that we set the metadata field to readonly.
            self.fields['metadata'].widget = HiddenInput()
