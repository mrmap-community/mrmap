from extras.viewsets import JSONDetailView
from registry.models.mapcontext import MapContext


class OwsContextView(JSONDetailView):
    model = MapContext

    def get_data(self, context):
        map_context: MapContext = self.get_object()
        return map_context.as_ows_context()
