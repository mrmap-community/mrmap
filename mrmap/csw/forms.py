from django import forms
from MrMap.forms import MrMapForm
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from csw.tasks import async_harvest
from structure.models import MrMapGroup


class HarvestGroupForm(MrMapForm):
    harvest_with_group = forms.ModelChoiceField(
        label=_("Harvest with group"),
        queryset=MrMapGroup.objects.none(),
        initial=1
    )

    def __init__(self, instance, *args, **kwargs):
        self.instance = instance
        super(HarvestGroupForm, self).__init__(*args, **kwargs)
        self.fields["harvest_with_group"].queryset = self.requesting_user.groups\
            .filter(mrmapgroup__is_public_group=False, mrmapgroup__is_permission_group=False)

    def process_harvest_catalogue(self):
        # Check if the catalogue exists
        async_harvest.delay(
            self.instance.id,
            self.cleaned_data['harvest_with_group'].id,
        )
        messages.success(
            self.request,
            "Harvesting starts!"
        )

