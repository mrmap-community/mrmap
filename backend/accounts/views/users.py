from accounts.models.users import User
from accounts.serializers.users import UserCreateSerializer, UserSerializer
from rest_framework.permissions import DjangoObjectPermissions
from rest_framework.response import Response
from rest_framework_extensions.mixins import NestedViewSetMixin
from rest_framework_json_api.schemas.openapi import AutoSchema
from rest_framework_json_api.views import ModelViewSet, RelationshipView


class UserRelationshipView(RelationshipView):
    schema = AutoSchema(
        tags=["Users"],
    )
    queryset = User.objects


class UserViewSet(NestedViewSetMixin, ModelViewSet):
    schema = AutoSchema(
        tags=['Users'],
    )
    queryset = User.objects.with_meta()
    serializer_classes = {
        "default": UserSerializer,
        "create": UserCreateSerializer,
    }
    permission_classes = [DjangoObjectPermissions]
    prefetch_for_includes = {
        '__all__': [],
        'groups': ['groups']
    }

    def get_serializer_class(self):
        return self.serializer_classes.get(
            self.action, self.serializer_classes["default"]
        )

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        new_data = response.data
        # FIXME: password attribute is still present in the rendered data, but with value null
        new_data.pop('password')
        return Response(new_data, status=response.status_code, headers=response.headers)
