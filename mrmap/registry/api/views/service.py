from extras.api.viewsets import StandardViewSet
from registry.api.serializers.service import LayerSerializer
from registry.models.service import Layer


class LayerViewSet(StandardViewSet):
    model = Layer
    default_serializer = LayerSerializer
