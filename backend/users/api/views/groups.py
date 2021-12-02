from django.contrib.auth.models import Group
from rest_framework_json_api.schemas.openapi import AutoSchema
from rest_framework_json_api.views import ModelViewSet

from users.api.filters.groups import OrganizationFilterSet
from users.api.serializers.groups import (GroupSerializer,
                                          OrganizationSerializer)
from users.models.groups import Organization


class GroupViewSet(ModelViewSet):
    schema = AutoSchema(
        tags=['Users'],
    )
    queryset = Group.objects.all()
    serializer_class = GroupSerializer


class OrganizationViewSet(ModelViewSet):
    schema = AutoSchema(
        tags=['Users'],
    )
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    filterset_class = OrganizationFilterSet
    search_fields = ('id', 'name')
