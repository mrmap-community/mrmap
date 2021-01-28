"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 09.03.20

"""
from dal import autocomplete
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpRequest
from django.utils.decorators import method_decorator

from service.helper.enums import MetadataEnum
from service.models import Keyword, Category, ReferenceSystem, Metadata, OGCOperation
from structure.models import MrMapGroup

from structure.permissionEnums import PermissionEnum
from users.helper.user_helper import get_user


@method_decorator(login_required, name='dispatch')
class KeywordAutocomplete(autocomplete.Select2QuerySetView):
    """ Provides an autocomplete functionality for keyword records

    """
    def get_queryset(self):
        """ Getter for the matching keywords

        Returns:
             records (QuerySet): The matched records
        """
        user = get_user(self.request)
        if user is None:
            return None

        records = Keyword.objects.all()
        query=""
        if self.q:
            # There are filtering parameters!
            query = self.q
        records = records.filter(keyword__icontains=query)

        return records

    def has_add_permission(self, request: HttpRequest):
        """ Checks whether the user is allowed to add new keywords

        Args:
            request (HttpRequest): THe incoming request
        Returns:
            True|False
        """
        user = get_user(request)

        perm = PermissionEnum.CAN_EDIT_METADATA
        is_editor = user.has_perm(perm)
        return user is not None and is_editor


@method_decorator(login_required, name='dispatch')
class CategoryAutocomplete(autocomplete.Select2QuerySetView):
    """ Provides an autocomplete functionality for categories records

    """
    def get_queryset(self):
        """ Getter for the matching categories

        Returns:
             records (QuerySet): The matched records
        """
        user = get_user(self.request)
        if user is None:
            return None

        records = Category.objects.all()
        query=""
        if self.q:
            # There are filtering parameters!
            query = self.q
        # ToDo: Find dynamic way to resolve user input language to correct variable
        records = records.filter(title_locale_1__icontains=query)

        return records


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
    def get_queryset(self):
        """ Getter for the matching categories

        Returns:
             records (QuerySet): The matched records
        """
        records = ReferenceSystem.objects.all()
        query = ""
        if self.q:
            # There are filtering parameters!
            query = self.q
        records = records.filter(
            Q(prefix__icontains=query)
            | Q(code__icontains=query)
        )

        return records

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
    def get_queryset(self):
        """ Getter for the matching OGCOperations

        Returns:
             records (QuerySet): The matched records
        """

        records = OGCOperation.objects.all()
        query = ""
        if self.q:
            # There are filtering parameters!
            query = self.q
        records = records.filter(
            Q(operation__icontains=query)
        )
        return records


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
