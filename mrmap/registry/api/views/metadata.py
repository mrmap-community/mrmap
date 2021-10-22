from django_filters import rest_framework as api_filters
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import DjangoModelPermissions

from extras.api.pagination import StandardResultsSetPagination
from extras.api.viewsets import ModelViewSetWithPermissionCheckerSerializerContext
from registry.api.filters.metadata import DatasetMetadataApiFilter
from registry.api.serializers.metadata import DatasetMetadataSerializer
from registry.models import DatasetMetadata


class DatasetMetadataViewSet(ModelViewSetWithPermissionCheckerSerializerContext):
    queryset = DatasetMetadata.objects.all()
    filterset_class = DatasetMetadataApiFilter
    filter_backends = [api_filters.DjangoFilterBackend, OrderingFilter]
    ordering_fields = ['title', 'abstract', 'id']
    pagination_class = StandardResultsSetPagination
    permission_classes = [DjangoModelPermissions]

    serializers = {
        'default': DatasetMetadataSerializer
    }

    def get_serializer_class(self):
        return self.serializers.get(self.action, self.serializers['default'])

    # TODO: add to mixin (not needed for now. Will come in handy when we need to start overwriting methods)
    # def get_serialized_status_ok_response(self, _queryset, _many=True, _status=status.HTTP_200_OK):
    #    serializer = self.get_serializer(_queryset, many=_many)
    #    return Response(data=serializer.data, status=_status)

    def get_queryset(self, *args, **kwargs):
        return super().get_queryset()
