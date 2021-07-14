from django_filters.views import FilterView
from main.views import SecuredDeleteView, SecuredUpdateView, SecuredCreateView, SecuredListMixin
from resourceNew.forms.mapcontext import MapContextForm
from resourceNew.models.mapcontext import MapContext
from resourceNew.tables.mapcontext import MapContextTable


class MapContextIndexView(SecuredListMixin, FilterView):
    model = MapContext
    table_class = MapContextTable
    filterset_fields = {'title': ['icontains'], }


class MapContextCreateView(SecuredCreateView):
    model = MapContext
    form_class = MapContextForm
    template_name = 'resourceNew/mapcontext/map_context_add.html'


class MapContextEditView(SecuredUpdateView):
    model = MapContext
    form_class = MapContextForm
    template_name = 'resourceNew/mapcontext/map_context_add.html'


class MapContextDeleteView(SecuredDeleteView):
    model = MapContext
