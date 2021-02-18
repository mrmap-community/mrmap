from dal import autocomplete
from django_filters import FilterSet, ModelMultipleChoiceFilter
from monitoring.models import HealthState, MonitoringRun
from service.helper.enums import MetadataEnum
from service.models import Metadata


class HealthStateTableFilterForm(FilterSet):
    metadata = ModelMultipleChoiceFilter(
        queryset=Metadata.objects.filter(metadata_type=MetadataEnum.SERVICE.value),
        widget=autocomplete.ModelSelect2Multiple(url='editor:autocomplete_metadata')
    )
    monitoring_run = ModelMultipleChoiceFilter(
        queryset=MonitoringRun.objects.all(),
        widget=autocomplete.ModelSelect2Multiple(url='monitoring:autocomplete_monitoring_run')
    )

    class Meta:
        model = HealthState
        fields = []
