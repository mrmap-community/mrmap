"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 09.03.20

"""
from dal import autocomplete
from django.db.models import Q
from django.http import HttpRequest

from service.helper.enums import MetadataEnum
from service.models import Keyword, Category, ReferenceSystem, Metadata

from structure.permissionEnums import PermissionEnum
from users.helper.user_helper import get_user


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
        is_editor = user.has_permission(perm)
        return user is not None and is_editor


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


class ReferenceSystemAutocomplete(autocomplete.Select2QuerySetView):
    """ Provides an autocomplete functionality for categories records

    """
    def get_queryset(self):
        """ Getter for the matching categories

        Returns:
             records (QuerySet): The matched records
        """
        records = ReferenceSystem.objects.all()
        query=""
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
