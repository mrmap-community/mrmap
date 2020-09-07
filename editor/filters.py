import django_filters
from django import forms
from django.utils.translation import gettext_lazy as _

from users.helper import user_helper


class EditorAccessFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(
        method='filter_search_over_all',
        label=_('Search')
    )
    mg = django_filters.BooleanFilter(
        method='filter_my_groups',
        widget=forms.CheckboxInput(),
        label=_("My groups")
    )
    mog = django_filters.BooleanFilter(
        method='filter_my_org_groups',
        widget=forms.CheckboxInput(),
        label=_("My organization's groups")
    )

    def filter_my_groups(self, queryset, name, value):
        """ Filters by user groups

        Args:
            queryset: The prior queryset
            name: The param name
            value: The param value
        Returns:
             queryset: The post queryset
        """
        if value:
            user = user_helper.get_user(self.request)
            user_groups = user.get_groups()
            queryset = queryset & user_groups

        return queryset

    def filter_my_org_groups(self, queryset, name, value):
        """ Filters by user's organization's groups

        Args:
            queryset: The prior queryset
            name: The param name
            value: The param value
        Returns:
             queryset: The post queryset
        """
        if value:
            user = user_helper.get_user(self.request)
            queryset = queryset.filter(
                organization=user.organization
            )

        return queryset

    @staticmethod
    def filter_search_over_all(queryset, name, value):  # parameter name is needed cause 3 values are expected
        return queryset.filter(name__icontains=value) | \
               queryset.filter(organization__organization_name__icontains=value)
