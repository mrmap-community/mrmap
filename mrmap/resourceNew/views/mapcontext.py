from django.urls import reverse_lazy
from django_filters.views import FilterView

from MrMap.messages import MAP_CONTEXT_SUCCESSFULLY_CREATED
from main.views import SecuredDeleteView, SecuredUpdateView, SecuredCreateView, SecuredListMixin
from resourceNew.forms.mapcontext import MapContextForm
from resourceNew.models.mapcontext import MapContext
from resourceNew.tables.mapcontext import MapContextTable


class MapContextListView(SecuredListMixin, FilterView):
    model = MapContext
    table_class = MapContextTable


class MapContextCreateView(SecuredCreateView):
    model = MapContext
    form_class = MapContextForm
    success_message = MAP_CONTEXT_SUCCESSFULLY_CREATED
    success_url = reverse_lazy('resourceNew:map_context_list')


# @method_decorator(login_required, name='dispatch')
# class MapContextCreateView(FormView):
#     form_class = formset_factory(form=MapContextLayerForm, extra=1)
#     template_name = 'resourceNew/mapcontext/map_context_add.html'
#     success_message = MAP_CONTEXT_SUCCESSFULLY_CREATED
#     success_url = reverse_lazy('resource:mapcontexts-index')
#
#     def get_initial(self):
#         forms = []
#         for layer in MapContextLayer.objects.all():
#             forms.append({
#                 'id': layer.id,
#                 'title': layer.title,
#                 'parent': layer.parent.id if layer.parent else '#'
#             })
#         if not forms:
#             forms.append({
#                 'id': 'j1_1',
#                 'title': '/',
#                 'parent': '#'
#             })
#         return forms
#
#     def form_valid(self, form):
#         # delete all layers, then insert (implement more effective synchronization if needed)
#         MapContextLayer.objects.all().delete()
#         # keep track of stored layers (they can parents of following layers)
#         id_to_db_layer = {}
#         for f in form:
#             data = f.cleaned_data
#             # only process forms that contain data
#             if data.get('id'):
#                 parent_db_layer = id_to_db_layer.get(data.get('parent'))
#                 layer = MapContextLayer(title=data.get('title'), parent=parent_db_layer)
#                 layer.save()
#                 id_to_db_layer[data.get('id')] = layer
#         return super(MapContextCreateView, self).form_valid(form)

class MapContextUpdateView(SecuredUpdateView):
    model = MapContext
    form_class = MapContextForm


class MapContextDeleteView(SecuredDeleteView):
    model = MapContext
