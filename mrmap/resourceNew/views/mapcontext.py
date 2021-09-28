from django.shortcuts import render
from django.urls import reverse_lazy
from django_filters.views import FilterView
from extra_views import CreateWithInlinesView, UpdateWithInlinesView

from main.views import SecuredDeleteView, SecuredListMixin
from resourceNew.forms.mapcontext import MapContextForm
from resourceNew.formsets.mapcontext import MapContextLayerInline
from resourceNew.models import DatasetMetadataRelation, Layer
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


def map_context_load_layers(request):
    dataset_metadata_id = request.GET.get('dataset_metadata')
    dataset_metadata_relation = DatasetMetadataRelation.objects.filter(dataset_metadata_id=dataset_metadata_id)
    if len(dataset_metadata_relation) > 0:
        layers = Layer.objects.filter(id__in=dataset_metadata_relation.values('layer'))
    else:
        layers = Layer.objects.none()
    return render(request, 'resourceNew/mapcontext/layer_dropdown_list.html', {'layers': layers})
