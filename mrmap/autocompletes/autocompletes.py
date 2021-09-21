from dal import autocomplete
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
from guardian.mixins import LoginRequiredMixin
from guardian.shortcuts import get_objects_for_user

from acl.models.acl import AccessControlList
from monitoring.models import MonitoringRun, MonitoringResult, HealthState
from registry.models import Service, Layer, FeatureType
from structure.models import Organization
from registry.models.metadata import Keyword, MetadataContact, ReferenceSystem
from registry.models.security import OGCOperation, ServiceAccessGroup


class CreateObjectMixin:
    add_perm = None

    def has_add_permission(self, request: HttpRequest):
        """ Checks whether the user is allowed to add new keywords

        Args:
            request (HttpRequest): THe incoming request
        Returns:
            True|False
        """
        if not self.add_perm:
            raise ImproperlyConfigured(_('If you provide add functionality you need to define `add_perm` param'))
        user = request.user
        return user.has_perm(perm=self.add_perm)


class SecuredAutocompleteMixin:
    def get_queryset(self):
        qs = super().get_queryset()
        qs = get_objects_for_user(user=self.request.user, perms=f'view_{self.model.__name__.lower()}', klass=qs)
        return qs


class KeywordAutocomplete(LoginRequiredMixin, CreateObjectMixin, autocomplete.Select2QuerySetView):
    model = Keyword
    search_fields = ['keyword']
    add_perm = "add_keyword"


class ServiceAutocomplete(SecuredAutocompleteMixin, LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = Service
    search_fields = ['metadata__title', 'id']


class ServiceAccessGroupAutocomplete(SecuredAutocompleteMixin, LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = ServiceAccessGroup
    search_fields = ['name', 'id']


class LayerAutocomplete(SecuredAutocompleteMixin, LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = Layer
    search_fields = ['metadata__title', 'id']


class FeatureTypeAutocomplete(SecuredAutocompleteMixin, LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = FeatureType
    search_fields = ['metadata__title', 'id']


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


class OperationsAutocomplete(LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = OGCOperation
    search_fields = ['operation']


class UsersAutocomplete(LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = get_user_model()
    search_fields = ['username']


class OrganizationAutocomplete(LoginRequiredMixin, SecuredAutocompleteMixin, autocomplete.Select2QuerySetView):
    model = Organization
    search_fields = ['name']


class PermissionsAutocomplete(LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = Permission
    search_fields = ['codename', 'name']

    def get_result_label(self, result):
        return result.name


class MonitoringRunAutocomplete(LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = MonitoringRun
    search_fields = ['uuid']


class MonitoringResultAutocomplete(LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = MonitoringResult
    search_fields = ['uuid']


class HealthStateAutocomplete(LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = HealthState
    search_fields = ['uuid']


class AccessControlListAutocomplete(LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = AccessControlList
    search_fields = ['uuid', 'name']
