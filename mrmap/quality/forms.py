from main.forms import ModelForm
from quality.models import ConformityCheckRun


class ConformityCheckRunModelForm(ModelForm):
    class Meta:
        model = ConformityCheckRun
        fields = ['dataset_metadata', 'config']
