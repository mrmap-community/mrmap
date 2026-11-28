from accounts.models.users import User
from accounts.permissions import (AccountAccessPermission,
                                  readable_accounts)
from accounts.serializers.users import UserCreateSerializer, UserSerializer
from rest_framework.response import Response
from rest_framework_json_api.views import ModelViewSet


class UserViewSetMixin:
    # the annotation carries the display string of the user, so the sort the
    # generic pickers send can be answered by the database (#1035)
    queryset = User.objects.with_meta().with_string_representation()
    serializer_classes = {
        "default": UserSerializer,
        "create": UserCreateSerializer,
    }
    # the read of an account is decided by the catalogue, which is what
    # ``DjangoObjectPermissions`` never asked on a safe method (#1807); the
    # write half of that class is inherited unchanged
    permission_classes = [AccountAccessPermission]
    prefetch_for_includes = {
        '__all__': [
            # the UserSerializer answers the roles relation of every user
            # (#736); this keeps that answer off a query per row
            'role_memberships__role__role_definition',
            'role_memberships__role__organization',
        ],
        'groups': ['groups']
    }
    search_fields = ("id", "username", "first_name", "last_name", "email")
    ordering_fields = ["id", "username", "first_name",
                       "last_name", "email", "is_active", "date_joined",
                       "string_representation"]
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        'username': ['exact', 'icontains', 'contains'],
        'first_name': ['exact', 'icontains', 'contains'],
        'last_name': ['exact', 'icontains', 'contains'],
        'email': ['exact', 'icontains', 'contains'],
    }

    def get_queryset(self):
        # the list answers the same rule as the detail route, so a row cannot
        # be hidden from the collection and reached by its id (#1807)
        return readable_accounts(
            self.request.user, super().get_queryset(), self.request)

    def get_serializer_class(self):
        return self.serializer_classes.get(
            self.action, self.serializer_classes["default"]
        )

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        new_data = response.data
        # FUTURE: password attribute is still present in the rendered data, but with value null
        new_data.pop('password')
        return Response(new_data, status=response.status_code, headers=response.headers)


class UserViewSet(
    UserViewSetMixin,
    ModelViewSet
):
    pass
