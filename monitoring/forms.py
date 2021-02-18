from dal import autocomplete
from django.forms import ModelForm
from monitoring.models import MonitoringRun
from service.models import Metadata


class MonitoringRunForm(ModelForm):
    class Meta:
        model = MonitoringRun
        fields = [
            "metadatas",
        ]
        widgets = {
            "metadatas": autocomplete.ModelSelect2Multiple(url='editor:metadata-autocomplete')
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # todo: filter by is_root = true
        self.fields['metadatas'].queryset = Metadata.objects.all()
