from dal import autocomplete
from guardian.mixins import LoginRequiredMixin
from registry.models.metadata import Keyword, MetadataContact, ReferenceSystem, Style
from extras.autocompletes import CreateObjectMixin, SecuredAutocompleteMixin
from registry.models import DatasetMetadata


class KeywordAutocomplete(LoginRequiredMixin, CreateObjectMixin, autocomplete.Select2QuerySetView):
    model = Keyword
    search_fields = ['keyword']
    add_perm = "add_keyword"


class MetadataContactAutocomplete(LoginRequiredMixin, SecuredAutocompleteMixin, autocomplete.Select2QuerySetView):
    model = MetadataContact
    search_fields = ['name']


class ReferenceSystemAutocomplete(LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = ReferenceSystem
    search_fields = ['prefix', 'code']

    def get_result_label(self, result):
        """
            we need to override this function to show the id of the metadata object,
            so the user can differentiate the results where title is equal.
        """
        return f'{result.prefix}{result.code}'


class DatasetMetadataAutocomplete(SecuredAutocompleteMixin, LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = DatasetMetadata
    search_fields = ['title']

    def get_queryset(self):
        qs = super().get_queryset()

        layer_pk = self.forwarded.get('layer', None)

        if layer_pk:
            qs = qs.filter(self_pointing_layers__pk=layer_pk)

        return qs


class StyleAutocomplete(SecuredAutocompleteMixin, LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = Style
    search_fields = ['title', 'name', 'id']

    def get_queryset(self):
        qs = super().get_queryset()

        layer_pk = self.forwarded.get('layer', None)

        if layer_pk:
            qs = qs.filter(layer__pk=layer_pk)

        return qs
