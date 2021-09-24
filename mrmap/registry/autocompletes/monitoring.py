from dal import autocomplete
from django.utils.translation import gettext_lazy as _
from guardian.mixins import LoginRequiredMixin
from monitoring.models import MonitoringRun, MonitoringResult, HealthState


class MonitoringRunAutocomplete(LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = MonitoringRun
    search_fields = ['uuid']


class MonitoringResultAutocomplete(LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = MonitoringResult
    search_fields = ['uuid']


class HealthStateAutocomplete(LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = HealthState
    search_fields = ['uuid']
