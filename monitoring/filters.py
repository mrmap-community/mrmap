from dal import autocomplete
from django.db.models import Q
from django_filters import FilterSet, ModelMultipleChoiceFilter, CharFilter
from monitoring.models import HealthState, MonitoringRun, MonitoringResult
from service.helper.enums import MetadataEnum
from service.models import Metadata
from django.utils.translation import gettext_lazy as _


class MonitoringResultTableFilter(FilterSet):
    q = CharFilter(
        method='search',
        label='Search',
    )
    metadata = ModelMultipleChoiceFilter(
        queryset=Metadata.objects.filter(metadata_type=MetadataEnum.SERVICE.value),
        widget=autocomplete.ModelSelect2Multiple(url='resource:autocomplete_metadata_service')
    )
    monitoring_run = ModelMultipleChoiceFilter(
        queryset=MonitoringRun.objects.all(),
        widget=autocomplete.ModelSelect2Multiple(url='monitoring:autocomplete_monitoring_run')
    )
    monitoring_result = ModelMultipleChoiceFilter(
        label=_('Monitoring result'),
        queryset=MonitoringResult.objects.all(),
        widget=autocomplete.ModelSelect2Multiple(url='monitoring:autocomplete_monitoring_result')
    )

    class Meta:
        model = MonitoringResult
        fields = ['available']

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        qs_filter = (
                Q(error_msg__icontains=value) |
                Q(monitored_uri__icontains=value)
        )
        return queryset.filter(qs_filter)


class HealthStateTableFilter(FilterSet):
    metadata = ModelMultipleChoiceFilter(
        queryset=Metadata.objects.filter(metadata_type=MetadataEnum.SERVICE.value),
        widget=autocomplete.ModelSelect2Multiple(url='resource:autocomplete_metadata_service')
    )
    monitoring_run = ModelMultipleChoiceFilter(
        queryset=MonitoringRun.objects.all(),
        widget=autocomplete.ModelSelect2Multiple(url='monitoring:autocomplete_monitoring_run')
    )
    health_state = ModelMultipleChoiceFilter(
        label=_('Health state'),
        queryset=HealthState.objects.all(),
        widget=autocomplete.ModelSelect2Multiple(url='monitoring:autocomplete_health_state')
    )

    class Meta:
        model = HealthState
        fields = ['health_state_code']
