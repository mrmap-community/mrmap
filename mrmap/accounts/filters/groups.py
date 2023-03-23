from accounts.models.groups import Organization
from django_filters.filterset import Filter, FilterSet
from guardian.shortcuts import get_objects_for_user


class OrganizationFilterSet(FilterSet):
    user_has_perm = Filter(method='get_user_has_perm')

    class Meta:
        model = Organization
        fields = {
            'name': ['exact', 'icontains', 'contains'],
            'description': ['exact', 'icontains', 'contains'],
        }

    def get_user_has_perm(self, queryset, name, value):
        perms = value.split(',') if ',' in value else value
        return get_objects_for_user(user=self.request.user, perms=perms, klass=queryset, accept_global_perms=False)
