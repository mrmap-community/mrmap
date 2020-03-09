"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 09.03.20

"""
from dal import autocomplete

from service.models import Keyword, Category
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
        records = records.filter(keyword__istartswith=query)

        return records


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
        records = records.filter(title_locale_1__istartswith=query)

        return records