from rest_framework.viewsets import ModelViewSet

from registry.api.serializers.mapcontext import MapContextSerializer
from registry.models import MapContext


class MapContextViewSet(ModelViewSet):
    serializer_class = MapContextSerializer
    queryset = MapContext.objects.all()
