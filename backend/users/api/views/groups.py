from django.contrib.auth.models import Group
from rest_framework_json_api.schemas.openapi import AutoSchema
from users.api.serializers.groups import OrganizationSerializer, GroupSerializer
from users.models.groups import Organization
from rest_framework_json_api.views import ModelViewSet


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
    filter_fields = {
        'id': ['exact', 'lt', 'gt', 'gte', 'lte', 'in'],
        'name': ['exact', 'icontains', 'contains'],
        'description': ['exact', 'icontains', 'contains'],
    }
    search_fields = ('id', 'name')
