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
