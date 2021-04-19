from django.forms import ModelForm
from dal import autocomplete
from django.utils.translation import gettext_lazy as _
from csw.models import HarvestResult
from service.helper.enums import MetadataEnum
from service.models import Metadata
<<<<<<< HEAD
from structure.models import PendingTask, Organization


class HarvestGroupForm(MrMapForm):
    harvest_with_organization = forms.ModelChoiceField(
        label=_("Harvest with organization"),
        queryset=Organization.objects.none(),
        initial=1
    )

    def __init__(self, instance, *args, **kwargs):
        self.instance = instance
        super(HarvestGroupForm, self).__init__(*args, **kwargs)
        self.fields["harvest_with_organization"].queryset = self.requesting_user.organization.get_publishable_organizations()

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
                    self.instance.pk,
                    self.request.user.pk,
                    self.cleaned_data['harvest_with_organization'].pk,
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
=======


class HarvestRunForm(ModelForm):
    class Meta:
        model = HarvestResult
        fields = ('metadata', )
        widgets = {
            'metadata': autocomplete.ModelSelect2(url='resource:autocomplete_metadata_catalouge')
        }
        labels = {
            'metadata': _('Resource'),
        }
        help_texts = {
            'metadata': _('Select one which will be harvested.'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['metadata'].queryset = Metadata.objects.filter(metadata_type=MetadataEnum.CATALOGUE.value)
>>>>>>> 6547e7f6ad710c8351a3ede267a054c17a44fa14
