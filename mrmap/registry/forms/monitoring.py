from extras.forms import ModelForm
from registry.models.monitoring import MonitoringRun


class MonitoringRunForm(ModelForm):
    class Meta:
        model = MonitoringRun
        fields = ["services", "layers", "feature_types", "dataset_metadatas"]
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
        # self.fields['metadatas'].queryset = Metadata.objects.filter(metadata_type=MetadataEnum.SERVICE.value)
