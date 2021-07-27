from main.forms import ModelForm
from quality.models import ConformityCheckRun, ConformityCheckConfiguration


class ConformityCheckRunModelForm(ModelForm):
    class Meta:
        model = ConformityCheckRun
        fields = ['metadata', 'conformity_check_configuration']
