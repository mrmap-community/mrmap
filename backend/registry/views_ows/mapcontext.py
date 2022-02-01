from django.db.models.query import Prefetch
from extras.viewsets import EmbeddedJsonDetailView, JSONDetailView
from mptt.utils import get_cached_trees
from registry.models.mapcontext import MapContext, MapContextLayer


class OwsContextView(EmbeddedJsonDetailView):

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
        prefetch_parents = Prefetch(
            "map_context_layers",
            # TODO: maybe there is a better way to select parents in dynamic depth
            queryset=MapContextLayer.objects.all().select_related(
                "parent",
                "parent__parent",
                "parent__parent__parent",
                "parent__parent__parent__parent").prefetch_related(prefetch_map_context_layer_last_history))

        qs = qs.prefetch_related(
            prefetch_parents, prefetch_map_context_last_history)
        return qs

    def get_data(self, context):
        map_context: MapContext = self.object
        return map_context.as_ows_context()
