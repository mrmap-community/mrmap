import copy

from django import forms

from extras.forms import ModelForm
from registry.models import ConformityCheckRun


class ConformityCheckRunModelForm(ModelForm):
    class Meta:
        model = ConformityCheckRun
        fields = [
            'config',
            *model._resource.fk_fields
        ]

    def __init__(self, request, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        # Get our metadata type
        metadata_type = list(request.GET.keys())[0] if request.GET else None

        # TODO: for some reason, passing the disable attribute to the widget, will result in the loss of clean_data
        #  for our metadata_type of interest. Still not sure why this happens. Keeping it commented for now.
        # self.fields[metadata_type].widget.attrs['disabled'] = True

        for field in self.fields:
            if metadata_type != field and field != 'config':
                # Hide the fields we don't want to show (All except Config and our Metadata Type of interest)
                self.fields[field].widget = forms.HiddenInput()
