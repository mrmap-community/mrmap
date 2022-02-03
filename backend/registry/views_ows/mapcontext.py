from django.db.models.query import Prefetch
from extras.viewsets import JSONDetailView
from registry.enums.service import OGCOperationEnum
from registry.models.mapcontext import MapContext, MapContextLayer
from registry.models.service import WebMapServiceOperationUrl


class OwsContextView(JSONDetailView):

    def get_queryset(self):

        qs = MapContext.objects.all()
        prefetch_map_context_last_history = Prefetch(
            'change_logs',
            queryset=qs.model.objects.filter_last_history(),
            to_attr='last_history')

        prefetch_map_context_layer_last_history = Prefetch(
            'change_logs',
            queryset=MapContextLayer.objects.filter_last_history(),
            to_attr='last_history')

        prefetch_get_map_url = Prefetch(
            "rendering_layer__service__operation_urls",
            queryset=WebMapServiceOperationUrl.objects.filter(
                operation=OGCOperationEnum.GET_MAP.value,
                method="Get"),
            to_attr="prefetched_get_map_operation_url"
        )
        prefetch_parents = Prefetch(
            "map_context_layers",
            # TODO: maybe there is a better way to select parents in dynamic depth
            queryset=MapContextLayer.objects.all().select_related(
                "parent",
                "parent__parent",
                "parent__parent__parent",
                "parent__parent__parent__parent",
                "rendering_layer",
                "rendering_layer__service"
            ).prefetch_related(prefetch_map_context_layer_last_history, prefetch_get_map_url))

        qs = qs.prefetch_related(
            prefetch_parents,
            prefetch_map_context_last_history)
        return qs

    def get_data(self, context):
        map_context: MapContext = self.object
        return map_context.as_ows_context()
