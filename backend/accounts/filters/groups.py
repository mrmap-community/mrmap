from accounts.models.groups import Organization
from django_filters import Filter, FilterSet
from extras.permissions import objects_for_user


class OrganizationFilterSet(FilterSet):
    user_has_perm = Filter(method='get_user_has_perm')

    class Meta:
        model = Organization
        fields = {
            'name': ['exact', 'icontains', 'contains'],
            'description': ['exact', 'icontains', 'contains'],
        }

    def get_user_has_perm(self, queryset, name, value):
        # the list axis of the one facade (#734): this filter decided with
        # ``accept_global_perms=False`` while other call sites decided with
        # ``True``; the policy constant is in ``extras/permissions.py`` now
        # and a platform role which holds the permission widens the answer,
        # as it does everywhere else
        perms = value.split(',') if ',' in value else value
        return objects_for_user(self.request.user, perms, queryset)
