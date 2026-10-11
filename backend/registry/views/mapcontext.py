from django.db.models.query import Prefetch
from extras.permissions import DjangoObjectPermissionsOrAnonReadOnly
from extras.viewsets import NestedModelViewSet, PreloadNotIncludesMixin
from registry.models import MapContext, MapContextLayer
from registry.serializers.mapcontext import (MapContextDefaultSerializer,
                                             MapContextIncludeSerializer,
                                             MapContextLayerSerializer)
from rest_framework_json_api.views import ModelViewSet


class MapContextViewSet(
    PreloadNotIncludesMixin,
    ModelViewSet
):
    queryset = MapContext.objects.all()
    serializer_classes = {
        'default': MapContextDefaultSerializer,
        'include': MapContextIncludeSerializer
    }
    prefetch_for_includes = {
        '__all__': [],
        'map_context_layers': ['map_context_layers']
    }
    prefetch_for_not_includes = {
        # without an include the layers of a mapcontext are only answered as
        # related resources, so only their ids are needed
        'map_context_layers': [
            Prefetch(
                "map_context_layers",
                queryset=MapContextLayer.objects.only("id", "map_context_id")
            )
        ]
    }
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    search_fields = ("id", "title", "abstract")
    filterset_fields = {
        'id': ['exact', 'in'],
        'title': ['exact', 'icontains', 'contains'],
        'abstract': ['exact', 'icontains', 'contains']
    }
    ordering_fields = ["id", "title", "abstract", ]

    def get_serializer_class(self):
        # if we detect include as queryparam, we need to switch the serializer,
        # cause the default serializer uses HyperlinkedRelatedField to render related fields.
        if self.request and 'include' in self.request.query_params:
            return self.serializer_classes["include"]
        return self.serializer_classes.get(
            self.action, self.serializer_classes["default"]
        )


class MapContextLayerViewSetMixin:
    # the mapcontext, the tree and the parent of a layer are always serialized
    queryset = MapContextLayer.objects.all().select_related(
        "map_context", "mptt_tree", "mptt_parent")
    serializer_class = MapContextLayerSerializer
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    # the rendering layer of a mapcontext layer is serialized in full when it is
    # included, without an include only its id is answered
    select_for_includes = {
        "rendering_layer": ["rendering_layer"],
        "map_context": ["map_context"],
    }
    search_fields = ("id", "title", "description", "keywords__keyword")
    filterset_fields = {
        'id': ['exact', 'in'],
        'title': ['exact', 'icontains', 'contains'],
        'description': ['exact', 'icontains', 'contains']
    }
    ordering_fields = ["id", "title", "description", ]


class MapContextLayerViewSet(
    MapContextLayerViewSetMixin,
    ModelViewSet
):
    pass


class NestedMapContextLayerViewSet(
    MapContextLayerViewSetMixin,
    NestedModelViewSet
):
    pass
