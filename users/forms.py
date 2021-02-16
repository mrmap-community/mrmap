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
from django.utils.translation import gettext_lazy as _
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

    def __init__(self, request: HttpRequest, *args, **kwargs):
        self.request = request
        super().__init__(*args, **kwargs)
        # don't touch this. User shall not be able to append groups here. For that, the request system is recommended.
        self.fields['groups'].queryset = self.request.user.get_groups()

    def clean(self):
        cleaned_data = super().clean()
        committed_groups = cleaned_data.get('groups')
        current_groups = self.request.user.get_groups()

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
