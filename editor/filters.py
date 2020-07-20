import django_filters
from django.utils.translation import gettext_lazy as _


class EditorAcessFilter(django_filters.FilterSet):
    editor_access_search = django_filters.CharFilter(method='filter_search_over_all',
                                                     label=_('Search'))

    @staticmethod
    def filter_search_over_all(queryset, name, value):  # parameter name is needed cause 3 values are expected

        return queryset.filter(name__icontains=value) | \
               queryset.filter(organization__organization_name__icontains=value)
