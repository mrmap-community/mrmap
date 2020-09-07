from django import forms
from django.core.exceptions import ObjectDoesNotExist

from MrMap.forms import MrMapForm
from django.utils.translation import gettext_lazy as _
from django.contrib import messages

from MrMap.messages import RESOURCE_NOT_FOUND
from csw.tasks import async_harvest

from service.helper.enums import MetadataEnum
from service.models import Metadata
from structure.models import PendingTask, MrMapGroup


class HarvestGroupForm(MrMapForm):
    harvest_with_group = forms.ModelChoiceField(
        label=_("Harvest with group"),
        queryset=MrMapGroup.objects.none(),
        initial=1
    )

    def __init__(self, instance, *args, **kwargs):
        self.instance = instance
        super(HarvestGroupForm, self).__init__(*args, **kwargs)
        self.fields["harvest_with_group"].queryset = self.requesting_user.get_groups(
            filter_by={
                "is_public_group": False,
                "is_permission_group": False
            }
        )

    def process_harvest_catalogue(self):
        # Check if the catalogue exists
        try:
            md = Metadata.objects.get(
                id=self.instance.id,
                metadata_type=MetadataEnum.CATALOGUE.value
            )
            # Check for a running pending task on this catalogue!
            try:
                p_t = PendingTask.objects.get(
                    task_id=str(md.id)
                )
                messages.info(
                    self.request,
                    "Harvesting is already running. Remaining time: {}".format(p_t.remaining_time)
                )
            except ObjectDoesNotExist:
                # No pending task exists, so we can start a harvesting process!
                async_harvest.delay(
                    self.instance.id,
                    self.cleaned_data['harvest_with_group'].id,
                )
                messages.success(
                    self.request,
                    "Harvesting starts!"
                )
        except ObjectDoesNotExist:
            messages.error(
                self.request,
                RESOURCE_NOT_FOUND
            )
