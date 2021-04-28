from dal import autocomplete
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
from guardian.mixins import LoginRequiredMixin
from guardian.shortcuts import get_objects_for_user

from monitoring.models import MonitoringRun, MonitoringResult, HealthState
from service.helper.enums import MetadataEnum
from service.models import Keyword, Category, ReferenceSystem, Metadata, OGCOperation
from structure.models import Organization
from structure.permissionEnums import PermissionEnum


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
    add_perm = PermissionEnum.CAN_EDIT_METADATA


class CategoryAutocomplete(LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = Category
    search_fields = ['title_locale_1']


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


class MetadataAutocomplete(LoginRequiredMixin, SecuredAutocompleteMixin, autocomplete.Select2QuerySetView):
    model = Metadata
    search_fields = ['title', 'id']
    metadata_type = None

    def get_queryset(self):
        qs = super().get_queryset()
        if self.metadata_type:
            qs = qs.filter(metadata_type=self.metadata_type.value)
        return qs

    def get_result_label(self, result):
        """
            we need to override this function to show the id of the metadata object,
            so the user can differentiate the results where title is equal.
        """
        return '{} #{}'.format(result.title, result.id)


class MetadataServiceAutocomplete(MetadataAutocomplete):
    metadata_type = MetadataEnum.SERVICE


class MetadataDatasetAutocomplete(MetadataAutocomplete):
    metadata_type = MetadataEnum.DATASET


class MetadataLayerAutocomplete(MetadataAutocomplete):
    metadata_type = MetadataEnum.LAYER


class MetadataFeaturetypeAutocomplete(MetadataAutocomplete):
    metadata_type = MetadataEnum.FEATURETYPE


class MetadataCatalougeAutocomplete(MetadataAutocomplete):
    metadata_type = MetadataEnum.CATALOGUE


class MonitoringRunAutocomplete(LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = MonitoringRun
    search_fields = ['uuid']


class MonitoringResultAutocomplete(LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = MonitoringResult
    search_fields = ['uuid']


class HealthStateAutocomplete(LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = HealthState
    search_fields = ['uuid']
