from dal import autocomplete
from guardian.mixins import LoginRequiredMixin
from extras.autocompletes import SecuredAutocompleteMixin
from registry.models.service import Service, FeatureType


class ServiceAutocomplete(SecuredAutocompleteMixin, LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = Service
    search_fields = ['metadata__title', 'id']

    def get_queryset(self):
        return super().get_queryset().select_related("metadata")


class FeatureTypeAutocomplete(SecuredAutocompleteMixin, LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = FeatureType
    search_fields = ['metadata__title', 'id']
