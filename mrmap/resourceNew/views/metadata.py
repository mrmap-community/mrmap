from MrMap.icons import get_icon, IconEnum
from main.views import SecuredCreateView, SecuredListMixin, SecuredDetailView
from resourceNew import tasks
from resourceNew.enums.service import OGCServiceEnum
from resourceNew.filtersets.metadata import DatasetMetadataFilterSet
from resourceNew.forms import RegisterServiceForm
from resourceNew.models import Service, ServiceType, DatasetMetadata
from django.urls import reverse_lazy, reverse
from django.conf import settings
from django.views.generic import FormView
from django_filters.views import FilterView
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext

from resourceNew.tables.metadata import DatasetMetadataTable


class DatasetMetadataListView(SecuredListMixin, FilterView):
    model = DatasetMetadata
    table_class = DatasetMetadataTable
    filterset_class = DatasetMetadataFilterSet
    queryset = model.objects.for_table_view()

    """def get_filterset_kwargs(self, *args):
        kwargs = super(WmsIndexView, self).get_filterset_kwargs(*args)
        if kwargs['data'] is None:
            kwargs['queryset'] = kwargs['queryset'].filter(service__is_root=True)
        return kwargs
    """

    def get_table(self, **kwargs):
        # set some custom attributes for template rendering
        table = super(DatasetMetadataListView, self).get_table(**kwargs)
        # whether whole services or single layers should be displayed, we have to exclude some columns
        """
        filter_by_show_layers = self.filterset.form_prefix + '-' + 'service__is_root'
        if filter_by_show_layers in self.filterset.data and self.filterset.data.get(filter_by_show_layers) == 'on':
            table.exclude = (
                'layers', 'featuretypes', 'last_harvested', 'collected_harvest_records', 'last_harvest_duration',)
        else:
            table.exclude = (
                'parent_service', 'featuretypes', 'last_harvested', 'collected_harvest_records', 'last_harvest_duration',)
        """
        # render_helper = RenderHelper(user_permissions=list(filter(None, self.request.user.get_all_permissions())))
        # table.actions = [render_helper.render_item(item=Metadata.get_add_resource_action())]
        return table
