from accounts.filters.groups import OrganizationFilterSet
from accounts.models.groups import Organization
from accounts.serializers.groups import GroupSerializer, OrganizationSerializer
from django.contrib.auth.models import Group
from django.db.models import F
from extras.viewsets import NestedModelViewSet
from rest_framework_json_api.views import ModelViewSet


class GroupViewSetMixin:
    queryset = Group.objects.all()
    serializer_class = GroupSerializer
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        'name': ['exact', 'icontains', 'contains'],
    }

    def get_queryset(self):
        queryset = super(GroupViewSetMixin, self).get_queryset()
        if "parent_lookup_user" in self.kwargs:
            queryset = queryset.filter(
                user__id=self.kwargs["parent_lookup_user"])
        return queryset


class GroupViewSet(
    GroupViewSetMixin,
    ModelViewSet
):
    pass


class NestedGroupViewSet(
    GroupViewSetMixin,
    NestedModelViewSet
):
    pass


class OrganizationViewSetMixin:
    # the pickers of the frontend render and sort by the display string the
    # serializer answers, which for an organization is its name (#1035)
    queryset = Organization.objects.annotate(string_representation=F("name"))
    serializer_class = OrganizationSerializer
    filterset_class = OrganizationFilterSet
    search_fields = ('id', 'name')
    ordering_fields = [
        "id", "name", "description", "person_name", "email", "phone",
        "facsimile", "city", "postal_code", "address_type", "address",
        "state_or_province", "country", "string_representation",
    ]


class OrganizationViewSet(
    OrganizationViewSetMixin,
    ModelViewSet
):
    pass


class NestedOrganizationViewSet(
    OrganizationViewSetMixin,
    NestedModelViewSet
):
    pass
