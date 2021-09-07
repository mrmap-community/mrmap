from dal import autocomplete
from django.forms import ModelForm
from monitoring.models import MonitoringRun
from django.utils.translation import gettext_lazy as _


class MonitoringRunForm(ModelForm):
    class Meta:
        model = MonitoringRun
        fields = "__all__"
        """
        fields = ('metadatas', )
        widgets = {
            'metadatas': autocomplete.ModelSelect2Multiple(url='autocompletes:metadata_service')
        }
        labels = {
            'metadatas': _('Resources'),
        }
        help_texts = {
            'metadatas': _('Select one or multiple resources which become checked.'),
        }"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        #self.fields['metadatas'].queryset = Metadata.objects.filter(metadata_type=MetadataEnum.SERVICE.value)
