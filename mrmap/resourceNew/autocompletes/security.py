from dal import autocomplete
from guardian.mixins import LoginRequiredMixin
from resourceNew.models.security import OGCOperation
from resourceNew.settings import SECURE_ABLE_WMS_OPERATIONS, SECURE_ABLE_WFS_OPERATIONS


class WmsOperationsAutocomplete(LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = OGCOperation
    search_fields = ['operation']

    def get_queryset(self):
        return super().get_queryset().filter(operation__in=SECURE_ABLE_WMS_OPERATIONS)


class WfsOperationsAutocomplete(LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = OGCOperation
    search_fields = ['operation']

    def get_queryset(self):
        return super().get_queryset().filter(operation__in=SECURE_ABLE_WFS_OPERATIONS)
