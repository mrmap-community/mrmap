from accounts.filters.groups import OrganizationFilterSet
from accounts.models.groups import Organization
from accounts.serializers.groups import GroupSerializer, OrganizationSerializer
from django.contrib.auth.models import Group
from extras.openapi import CustomAutoSchema
from extras.viewsets import NestedModelViewSet
from rest_framework_json_api.views import ModelViewSet


class GroupViewSetMixin():
    schema = CustomAutoSchema(
        tags=['Users'],
    )
    queryset = Group.objects.all()
    serializer_class = GroupSerializer

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


class OrganizationViewSetMixin():
    schema = CustomAutoSchema(
        tags=['Users'],
    )
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    filterset_class = OrganizationFilterSet
    search_fields = ('id', 'name')


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
