from extras.forms import ModelForm
from registry.models import ConformityCheckRun


class ConformityCheckRunModelForm(ModelForm):
    class Meta:
        model = ConformityCheckRun
        fields = ['config', *model._resource.fk_fields]
