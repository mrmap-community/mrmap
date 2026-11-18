from accounts.filters.groups import OrganizationFilterSet
from accounts.models.groups import Organization
from accounts.serializers.groups import GroupSerializer, OrganizationSerializer
from django.contrib.auth.models import Group
from django.db.models import F
from extras.viewsets import NestedModelViewSet
from rest_framework.permissions import DjangoObjectPermissions
from rest_framework_json_api.views import ModelViewSet


class GroupViewSetMixin:
    # the serializer answers the members of every group it shows, so the rows
    # of the relation are read once per page instead of once per group (#1448)
    queryset = Group.objects.all().prefetch_related("user_set")
    serializer_class = GroupSerializer
    # the same class as the users endpoint (#1448): object permissions are
    # granted to the role groups of the organizations (#732), so a group whose
    # membership anybody may write hands out whatever those groups may do -
    # across every organization. Writing the membership is the members
    # endpoint of #736, which asks the organization it belongs to.
    permission_classes = [DjangoObjectPermissions]
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
    # an organization answers the contact fields of a real person, and its
    # group is the membership which decides whose role groups grant what:
    # reading it needs an identity and writing it is decided per object, like
    # on the users endpoint (#1448)
    permission_classes = [DjangoObjectPermissions]
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
