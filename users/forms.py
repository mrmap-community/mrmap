"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 28.05.19

"""
from dal import autocomplete
from django import forms
from django.forms import HiddenInput
from users.models import Subscription


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
