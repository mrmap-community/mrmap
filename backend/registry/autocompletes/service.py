from dal import autocomplete
from guardian.mixins import LoginRequiredMixin
from extras.autocompletes import SecuredAutocompleteMixin
from registry.models.service import Service, FeatureType, Layer


class ServiceAutocomplete(SecuredAutocompleteMixin, LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = Service
    search_fields = ['title', 'id']

    def get_queryset(self):
        return super().get_queryset().select_related("metadata")


class LayerAutocomplete(SecuredAutocompleteMixin, LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = Layer
    search_fields = ['title', 'id']

    def get_queryset(self):
        qs = super().get_queryset()

        dataset_metadata_pk = self.forwarded.get('dataset_metadata', None)

        if dataset_metadata_pk:
            qs = qs.filter(dataset_metadata__pk=dataset_metadata_pk)

        return qs


class FeatureTypeAutocomplete(SecuredAutocompleteMixin, LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = FeatureType
    search_fields = ['title', 'id']
