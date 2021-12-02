from django_filters.filterset import Filter, FilterSet
from rest_framework_gis.filters import GeometryFilter
from users.models.groups import Organization


class OrganizationFilterSet(FilterSet):
    can_publish_for = Filter(method='bbox_lat_lon_contains')

    class Meta:
        model = Organization
        fields = {
            'name': ['exact', 'icontains', 'contains'],
            'description': ['exact', 'icontains', 'contains'],
        }

    def can_publish_for(self, queryset, name, value):
        # TODO: filter given user(value)
        # queryset = get_objects_for_group(group=self,
        #                                  perms='users.can_publish_for_organization')

        return queryset
