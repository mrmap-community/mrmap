from django.db.models.query import Prefetch
from extras.viewsets import JSONDetailView
from registry.enums.service import HttpMethodEnum, OGCOperationEnum
from registry.models.mapcontext import MapContext, MapContextLayer
from registry.models.service import WebMapServiceOperationUrl


class OwsContextView(JSONDetailView):

    def get_queryset(self):

        qs = MapContext.objects.all()
        prefetch_map_context_last_history = Prefetch(
            'change_logs',
            queryset=MapContext.change_log.order_by("id", "-history_date", "-history_id").distinct("id").select_related("history_user"),
            to_attr='last_history')

        prefetch_map_context_layer_last_history = Prefetch(
            'change_logs',
            queryset=MapContextLayer.change_log.order_by("id", "-history_date", "-history_id").distinct("id").select_related("history_user"),
            to_attr='last_history')

        prefetch_get_map_url = Prefetch(
            "rendering_layer__service__operation_urls",
            queryset=WebMapServiceOperationUrl.objects.filter(
                operation=OGCOperationEnum.GET_MAP.value,
                method=HttpMethodEnum.GET.value),
            to_attr="prefetched_get_map_operation_url"
        )
        prefetch_layers = Prefetch(
            "map_context_layers",
            queryset=MapContextLayer.objects.all().select_related(
                "rendering_layer", "rendering_layer__service", "layer_style",
                "selection_layer", "selection_layer__service"
            ).prefetch_related(prefetch_map_context_layer_last_history, prefetch_get_map_url))

        qs = qs.prefetch_related(
            prefetch_layers,
            prefetch_map_context_last_history)
        return qs

    def get_data(self, context):
        map_context: MapContext = self.object
        return map_context.as_ows_context(request=self.request)
