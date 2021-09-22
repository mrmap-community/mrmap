from dal import autocomplete
from guardian.mixins import LoginRequiredMixin

from autocompletes.autocompletes import SecuredAutocompleteMixin
from resourceNew.models import DatasetMetadata, LayerMetadata


class DatasetMetadataAutocomplete(SecuredAutocompleteMixin, LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = DatasetMetadata
    search_fields = ['title']

    # The id
    def get_result_value(self, item):
        return item.id

    # The text to display
    def get_result_label(self, item):
        return item.title

    # The text of the selected option
    def get_selected_result_label(self, item):
        return item.id


class LayerMetadataAutocomplete(SecuredAutocompleteMixin, LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = LayerMetadata
    search_fields = ['title']

    # TODO: Define queryset to filter by selected dataset metadata option

    # The id
    def get_result_value(self, item):
        return item.id

    # The text to display
    def get_result_label(self, item):
        return item.title

    # The text of the selected option
    def get_selected_result_label(self, item):
        return item.id
