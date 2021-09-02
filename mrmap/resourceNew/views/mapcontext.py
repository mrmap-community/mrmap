from django.urls import reverse_lazy
from django_filters.views import FilterView
from extra_views import CreateWithInlinesView, UpdateWithInlinesView

from main.views import SecuredDeleteView, SecuredListMixin
from resourceNew.forms.mapcontext import MapContextForm
from resourceNew.formsets.mapcontext import MapContextLayerInline
from resourceNew.models.mapcontext import MapContext
from resourceNew.tables.mapcontext import MapContextTable


class MapContextListView(SecuredListMixin, FilterView):
    model = MapContext
    table_class = MapContextTable


# TODO SecuredCreateWithInlinesView ?
class MapContextCreateView(CreateWithInlinesView):
    model = MapContext
    form_class = MapContextForm
    inlines = [MapContextLayerInline]
    # TODO check if we can turn this into a generic template
    template_name = 'resourceNew/mapcontext/mapcontext_form.html'
    success_url = reverse_lazy('resourceNew:map_context_list')


# TODO SecuredUpdateWithInlinesView ?
class MapContextUpdateView(UpdateWithInlinesView):
    model = MapContext
    form_class = MapContextForm
    inlines = [MapContextLayerInline]
    # TODO check if we can turn this into a generic template
    template_name = 'resourceNew/mapcontext/mapcontext_form.html'
    success_url = reverse_lazy('resourceNew:map_context_list')


class MapContextDeleteView(SecuredDeleteView):
    model = MapContext
