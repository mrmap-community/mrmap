import django_filters
from service.models import Metadata


class WmsFilter(django_filters.FilterSet):
    wms_search = django_filters.CharFilter(method='filter_search_over_all',
                                          label='Search')

    @staticmethod
    def filter_search_over_all(queryset, name, value):  # parameter name is needed cause 3 values are expected

        return queryset.filter(title__icontains=value) | \
               queryset.filter(contact__organization_name__icontains=value) | \
               queryset.filter(service__created_by__name__icontains=value) | \
               queryset.filter(service__published_for__organization_name__icontains=value) | \
               queryset.filter(created__icontains=value)

    class Meta:
        model = Metadata
        fields = []
