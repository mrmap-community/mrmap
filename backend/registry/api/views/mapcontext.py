from rest_framework.permissions import DjangoModelPermissions
from django_filters import rest_framework as api_filters
from rest_framework.filters import OrderingFilter

from extras.api.pagination import StandardResultsSetPagination
from extras.api.viewsets import ModelViewSetWithPermissionChecker
from registry.api.filters.mapcontext import MapContextApiFilter
from registry.api.serializers.mapcontext import MapContextSerializer
from registry.models import MapContext


class MapContextViewSet(ModelViewSetWithPermissionChecker):
    queryset = MapContext.objects.all()
    filterset_class = MapContextApiFilter
    filter_backends = [api_filters.DjangoFilterBackend, OrderingFilter]
    ordering_fields = ['title', 'abstract', 'id']
    pagination_class = StandardResultsSetPagination
    permission_classes = [DjangoModelPermissions]

    serializers = {
        'default': MapContextSerializer
    }

    def get_serializer_class(self):
        return self.serializers.get(self.action, self.serializers['default'])

    # TODO: add to mixin (not needed for now. Will come in handy when we need to start overwriting methods)
    # def get_serialized_status_ok_response(self, _queryset, _many=True, _status=status.HTTP_200_OK):
    #    serializer = self.get_serializer(_queryset, many=_many)
    #    return Response(data=serializer.data, status=_status)

    def get_queryset(self, *args, **kwargs):
        return super().get_queryset()
