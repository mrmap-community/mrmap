from django.forms import ModelForm
from dal import autocomplete
from django.utils.translation import gettext_lazy as _
from csw.models import HarvestResult


class HarvestRunForm(ModelForm):
    class Meta:
        model = HarvestResult
        fields = "__all__"
        # FIXME: service app is outdated. Move to resource app
        """
        fields = ('metadata', )
        widgets = {
            'metadata': autocomplete.ModelSelect2(url='autocompletes:metadata_catalouge')
        }
        labels = {
            'metadata': _('Resource'),
        }
        help_texts = {
            'metadata': _('Select one which will be harvested.'),
        }"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        #self.fields['metadata'].queryset = Metadata.objects.filter(metadata_type=MetadataEnum.CATALOGUE.value)
