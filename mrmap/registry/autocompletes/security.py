from dal import autocomplete
from guardian.mixins import LoginRequiredMixin
from extras.autocompletes import SecuredAutocompleteMixin
from registry.models.security import OGCOperation, AllowedOperation, ServiceAccessGroup
from registry.settings import SECURE_ABLE_WMS_OPERATIONS, SECURE_ABLE_WFS_OPERATIONS


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


class SecureAbleOperationsAutocomplete(LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = OGCOperation
    search_fields = ['operation']

    def get_queryset(self):
        return super().get_queryset().filter(operation__in=SECURE_ABLE_WMS_OPERATIONS + SECURE_ABLE_WFS_OPERATIONS)


class AllowedOperationsAutocomplete(SecuredAutocompleteMixin, LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = AllowedOperation
    search_fields = ['id', ]


class ServiceAccessGroupAutocomplete(SecuredAutocompleteMixin, LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = ServiceAccessGroup
    search_fields = ['name', 'id']
