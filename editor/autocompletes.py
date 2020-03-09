"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 09.03.20

"""
from dal import autocomplete

from service.models import Keyword
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
            # We will receive requests in here with content as "kw1,kw2,kw" and we want to get suggestions for the last "kw"
            query = self.q.split(",")[-1]
        records = records.filter(keyword__istartswith=query)

        return records