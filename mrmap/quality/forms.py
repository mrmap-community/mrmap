from main.forms import ModelForm
from quality.models import ConformityCheckRun


class ConformityCheckRunModelForm(ModelForm):
    class Meta:
        model = ConformityCheckRun
        fields = ['config', *model._resource.fk_fields]
