from django.contrib.auth.models import Group
from users.api.serializers.groups import OrganizationSerializer, GroupSerializer
from users.models.groups import Organization
from rest_framework_json_api.views import ModelViewSet


class GroupViewSet(ModelViewSet):
    queryset = Group.objects.all()
    serializer_class = GroupSerializer


class OrganizationViewSet(ModelViewSet):
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
