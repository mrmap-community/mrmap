import django_filters
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.forms import TextInput, CheckboxInput, ChoiceField, CharField, CheckboxSelectMultiple, BooleanField
from structure.models import MrMapGroup, Organization


class GroupFilter(django_filters.FilterSet):
    # gsearch = Group search over all method
    gsearch = django_filters.CharFilter(method='filter_search_over_all',
                                        label=_('Search'))

    @staticmethod
    def filter_search_over_all(queryset, name, value): # parameter name is needed cause 3 values are expected
        return queryset.filter(name__icontains=value) | \
               queryset.filter(description__icontains=value) | \
               queryset.filter(organization__organization_name__icontains=value)

    class Meta:
        model = MrMapGroup
        fields = []


class OrganizationFilter(django_filters.FilterSet):
    # osearch = Organization search over all method
    osearch = django_filters.CharFilter(method='filter_search_over_all',
                                        label=_('Search'))

    # oiag = Organization is_auto_generated
    oiag = django_filters.BooleanFilter(field_name='is_auto_generated',
                                        method='filter_oiag',
                                        widget=CheckboxInput(),
                                        label=_('Show all organizations')
                                        )

    @staticmethod
    def filter_oiag(queryset, name, value):
        """ Filters by is_auto_generated

        Excludes organization records which do not hold proper organization_name values.

        Args:
            queryset: The queryset to be filtered
            name: The parameter name
            value: The parameter value
        Returns:

        """
        if value:
            # Do not filter anything, show all!
            pass
        else:
            queryset = queryset.filter(is_auto_generated=False)

        queryset = queryset.exclude(
            Q(organization_name="") |
            Q(organization_name=None)
        )
        return queryset

    @staticmethod
    def filter_search_over_all(queryset, name, value): # parameter name is needed cause 3 values are expected
        return queryset.filter(organization_name__icontains=value) | \
               queryset.filter(description__icontains=value) | \
               queryset.filter(parent__organization_name__icontains=value)

    class Meta:
        model = Organization
        fields = []
