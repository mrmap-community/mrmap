from rest_framework_json_api.schemas.openapi import AutoSchema
from users.api.serializers.users import MrMapUserSerializer
from users.models.users import MrMapUser
from rest_framework_extensions.mixins import NestedViewSetMixin
from rest_framework_json_api.views import ModelViewSet


class MrMapUserViewSet(NestedViewSetMixin, ModelViewSet):
    schema = AutoSchema(
        tags=['Users'],
    )
    queryset = MrMapUser.objects.all()
    serializer_class = MrMapUserSerializer
    prefetch_for_includes = {
        '__all__': [],
        'groups': ['groups']
    }
