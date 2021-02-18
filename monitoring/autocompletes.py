from dal import autocomplete
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from monitoring.models import MonitoringRun, HealthState, MonitoringResult


@method_decorator(login_required, name='dispatch')
class MonitoringRunAutocomplete(autocomplete.Select2QuerySetView):
    """ Provides an autocomplete functionality for dataset monitoring run records

    """
    model = MonitoringRun
    search_fields = ['uuid']


@method_decorator(login_required, name='dispatch')
class MonitoringResultAutocomplete(autocomplete.Select2QuerySetView):
    """ Provides an autocomplete functionality for dataset monitoring result records

    """
    model = MonitoringResult
    search_fields = ['uuid']


@method_decorator(login_required, name='dispatch')
class HealthStateAutocomplete(autocomplete.Select2QuerySetView):
    """ Provides an autocomplete functionality for dataset health state records

    """
    model = HealthState
    search_fields = ['uuid']
