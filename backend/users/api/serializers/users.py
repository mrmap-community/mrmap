from django.contrib.auth.models import Group
from users.api.serializers.groups import GroupSerializer
from users.models.users import MrMapUser
from rest_framework_json_api.serializers import ModelSerializer
from rest_framework.relations import HyperlinkedIdentityField


class MrMapUserSerializer(ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='users:mrmapuser-detail',
    )

    included_serializers = {
        'groups': GroupSerializer,
    }

    class Meta:
        model = MrMapUser
        fields = "__all__"
