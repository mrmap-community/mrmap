import django_filters.rest_framework
from django.core.exceptions import ImproperlyConfigured
from rest_framework import status
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from extras.api.pagination import StandardResultsSetPagination


class StandardViewSet(ModelViewSet):
    model = None 
    default_serializer = None
    pagination_class = StandardResultsSetPagination
    # filterset_class = None  # TODO
    # permission_classes = None # TODO

    serializers = {
        'default': default_serializer
    }

    def get_model_class(self):
        if not self.model:
            raise ImproperlyConfigured("model class is missing!")
        return self.model

    def get_serializer_class(self):
        serializer = self.serializers.get(self.action, self.default_serializer)
        if not serializer:
            raise ImproperlyConfigured("even 'default_serializer' must be configured!")        
        return serializer

    def get_serialized_status_ok_response(self, _queryset, _many=True, _status=status.HTTP_200_OK):
        serializer = self.get_serializer(_queryset, many=_many)
        return Response(data=serializer.data, status=_status)

    def get_queryset(self, *args, **kwargs):
        # TODO: filter objects by object permissions
        return self.model.objects.all()
