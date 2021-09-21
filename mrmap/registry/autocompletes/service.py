from dal import autocomplete
from guardian.mixins import LoginRequiredMixin

from extras.autocompletes import SecuredAutocompleteMixin
from registry.models import Service


class ServiceAutocomplete(SecuredAutocompleteMixin, LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = Service
    search_fields = ['title', 'id']

    def get_queryset(self):
        return super().get_queryset().select_related("metadata")
