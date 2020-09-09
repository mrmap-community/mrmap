"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 08.09.20

"""
import django_filters
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from structure.models import MrMapUser


class MrMapUserFilter(django_filters.FilterSet):
    us = django_filters.CharFilter(
        help_text=_("Search for a user or organization name. Input <strong>must</strong> contain at least 3 characters."),
        method='filter_search_over_all',
        label=_('Search')
    )

    def filter_search_over_all(self, qs, name, value):
        """ Filters on usernames and organizations

        Only filters if given value is at least 3 characters large, to prevent listing of too much users.

        Args:
            qs:
            name:
            value:
        Returns:
             qs
        """
        if qs.count() == 0 and len(value) >= 3:
            # If qs is objects.none() and filter value has a minimum length
            qs = self.all_users
        qs = qs.filter(
            Q(username__icontains=value) | Q(organization__organization_name__icontains=value)
        )
        return qs

    class Meta:
        model = MrMapUser
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.all_users = MrMapUser.objects.filter(
            is_active=True
        )
