from dal import autocomplete
from django.db.models import Q
import django_filters
from django_filters import FilterSet, CharFilter, ModelMultipleChoiceFilter

from monitoring.models import HealthState, MonitoringRun, MonitoringResult
from service.helper.enums import MetadataEnum
from service.models import Metadata
from django.utils.translation import gettext_lazy as _


class MonitoringRunTableFilter(django_filters.FilterSet):
    metadatas = django_filters.ModelMultipleChoiceFilter(
        queryset=Metadata.objects.filter(metadata_type=MetadataEnum.SERVICE.value),
        widget=autocomplete.ModelSelect2Multiple(url='autocompletes:metadata_service')
    )
    monitoring_result = django_filters.ModelMultipleChoiceFilter(
        label=_('Monitoring result'),
        queryset=MonitoringResult.objects.all(),
        widget=autocomplete.ModelSelect2Multiple(url='autocompletes:monitoring_result')
    )
    health_state = django_filters.ModelMultipleChoiceFilter(
        label=_('Health state'),
        queryset=MonitoringResult.objects.all(),
        widget=autocomplete.ModelSelect2Multiple(url='autocompletes:monitoring.healthstate')
    )

    class Meta:
        model = MonitoringRun
        fields = ['uuid']


class MonitoringResultTableFilter(FilterSet):
    q = CharFilter(
        method='search',
        label='Search',
    )
    metadata = ModelMultipleChoiceFilter(
        queryset=Metadata.objects.filter(metadata_type=MetadataEnum.SERVICE.value),
        widget=autocomplete.ModelSelect2Multiple(url='autocompletes:metadata_service')
    )
    monitoring_run = ModelMultipleChoiceFilter(
        queryset=MonitoringRun.objects.all(),
        widget=autocomplete.ModelSelect2Multiple(url='autocompletes:monitoring_run')
    )
    monitoring_result = ModelMultipleChoiceFilter(
        label=_('Monitoring result'),
        queryset=MonitoringResult.objects.all(),
        widget=autocomplete.ModelSelect2Multiple(url='autocompletes:monitoring_result')
    )

    class Meta:
        model = MonitoringResult
        fields = ['q', 'available']

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
        widget=autocomplete.ModelSelect2Multiple(url='autocompletes:metadata_service')
    )
    monitoring_run = ModelMultipleChoiceFilter(
        queryset=MonitoringRun.objects.all(),
        widget=autocomplete.ModelSelect2Multiple(url='autocompletes:monitoring_run')
    )
    health_state = ModelMultipleChoiceFilter(
        label=_('Health state'),
        queryset=HealthState.objects.all(),
        widget=autocomplete.ModelSelect2Multiple(url='autocompletes:health_state')
    )

    class Meta:
        model = HealthState
        fields = ['health_state_code']
