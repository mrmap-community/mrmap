"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 09.03.20

"""
from dal import autocomplete
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Q
from django.http import HttpRequest
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from service.helper.enums import MetadataEnum
from service.models import Keyword, Category, ReferenceSystem, Metadata, OGCOperation
from structure.models import MrMapGroup, MrMapUser

from structure.permissionEnums import PermissionEnum
from users.helper.user_helper import get_user


class AutocompleteView(autocomplete.Select2QuerySetView):
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
        return user.has_perm(self.add_perm)


@method_decorator(login_required, name='dispatch')
class KeywordAutocomplete(AutocompleteView):
    """ Provides an autocomplete functionality for keyword records
    """
    model = Keyword
    search_fields = ['keyword']
    add_perm = PermissionEnum.CAN_EDIT_METADATA


@method_decorator(login_required, name='dispatch')
class CategoryAutocomplete(autocomplete.Select2QuerySetView):
    """ Provides an autocomplete functionality for categories records

    """
    model = Category
    search_fields = ['title_locale_1']


@method_decorator(login_required, name='dispatch')
class MetadataAutocomplete(autocomplete.Select2QuerySetView):
    """ Provides an autocomplete functionality for dataset metadata records

    """
    model = Metadata
    search_fields = ['title', 'id']

    def get_result_label(self, result):
        """
            we need to override this function to show the id of the metadata object,
            so the user can differentiate the results where title is equal.
        """
        return '{} #{}'.format(result.title, result.id)


@method_decorator(login_required, name='dispatch')
class DatasetMetadataAutocomplete(autocomplete.Select2QuerySetView):
    """ Provides an autocomplete functionality for dataset metadata records

    """
    def get_queryset(self):
        """ Getter for the matching metadatas

        Returns:
             records (QuerySet): The matched records
        """
        user = get_user(self.request)
        if user is None:
            return None

        records = user.get_metadatas_as_qs(type=MetadataEnum.DATASET, inverse_match=True)
        query = ""
        if self.q:
            # There are filtering parameters!
            query = self.q
        records = records.filter(
            Q(title__icontains=query) |
            Q(id__icontains=query)
        )

        return records

    def get_result_label(self, result):
        """
            we need to override this function to show the id of the metadata object,
            so the user can differentiate the results where title is equal.
        """
        return '{} #{}'.format(result.title, result.id)


@method_decorator(login_required, name='dispatch')
class ServiceMetadataAutocomplete(autocomplete.Select2QuerySetView):
    """ Provides an autocomplete functionality for dataset metadata records

    """
    def get_queryset(self):
        """ Getter for the matching metadatas

        Returns:
             records (QuerySet): The matched records
        """
        user = get_user(self.request)
        if user is None:
            return None

        records = Metadata.objects.filter(
            metadata_type=MetadataEnum.SERVICE.value,
            is_active=True,
        )
        query = ""
        if self.q:
            # There are filtering parameters!
            query = self.q
        records = records.filter(
            Q(title__icontains=query) |
            Q(id__icontains=query)
        )

        return records

    def get_result_label(self, result):
        """
            we need to override this function to show the id of the metadata object,
            so the user can differentiate the results where title is equal.
        """
        return '{} #{}'.format(result.title, result.id)


@method_decorator(login_required, name='dispatch')
class ReferenceSystemAutocomplete(autocomplete.Select2QuerySetView):
    """ Provides an autocomplete functionality for categories records

    """
    model = ReferenceSystem
    search_fields = ['prefix', 'code']

    def get_result_label(self, result):
        """
            we need to override this function to show the id of the metadata object,
            so the user can differentiate the results where title is equal.
        """
        return f'{result.prefix}{result.code}'


@method_decorator(login_required, name='dispatch')
class OperationsAutocomplete(autocomplete.Select2QuerySetView):
    """ Provides an autocomplete functionality for categories records

    """
    model = OGCOperation
    search_fields = ['operation']


@method_decorator(login_required, name='dispatch')
class GroupsAutocomplete(autocomplete.Select2QuerySetView):
    """ Provides an autocomplete functionality for categories records

    """
    def get_queryset(self):
        """ Getter for the matching groups

        Returns:
             records (QuerySet): The matched records
        """
        records = MrMapGroup.objects.filter(Q(is_permission_group=False) | Q(is_public_group=True))
        query = ""
        if self.q:
            # There are filtering parameters!
            query = self.q
        records = records.filter(
            Q(name__icontains=query)
        )
        return records


@method_decorator(login_required, name='dispatch')
class UsersAutocomplete(autocomplete.Select2QuerySetView):
    """ Provides an autocomplete functionality for user records

    """
    model = MrMapUser
    search_fields = ['username']

