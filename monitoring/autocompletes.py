from dal import autocomplete
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from monitoring.models import MonitoringRun


@method_decorator(login_required, name='dispatch')
class MonitoringRunAutocomplete(autocomplete.Select2QuerySetView):
    """ Provides an autocomplete functionality for dataset metadata records

    """
    model = MonitoringRun
    search_fields = ['uuid']
