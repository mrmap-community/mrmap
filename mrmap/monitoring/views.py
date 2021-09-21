from django.utils.translation import gettext_lazy as _
from django_filters.views import FilterView

from MrMap.messages import MONITORING_RUN_SCHEDULED
from extras.views import SecuredListMixin, SecuredCreateView, SecuredDetailView
from monitoring.filters import HealthStateTableFilter, MonitoringResultTableFilter, MonitoringRunTableFilter
from monitoring.forms import MonitoringRunForm
from monitoring.models import MonitoringRun, MonitoringResult, HealthState
from monitoring.tables import MonitoringResultTable, MonitoringRunTable, MonitoringResultDetailTable, HealthStateTable, \
    HealthStateDetailTable


class MonitoringRunTableView(SecuredListMixin, FilterView):
    model = MonitoringRun
    table_class = MonitoringRunTable
    filterset_class = MonitoringRunTableFilter
    queryset = MonitoringRun.objects.prefetch_related("services", "layers", "feature_types", "dataset_metadatas",
                                                      "health_states", "services__service_type", "services__metadata")


class MonitoringRunNewView(SecuredCreateView):
    model = MonitoringRun
    form_class = MonitoringRunForm
    success_message = MONITORING_RUN_SCHEDULED


class MonitoringResultTableView(SecuredListMixin, FilterView):
    model = MonitoringResult
    table_class = MonitoringResultTable
    filterset_class = MonitoringResultTableFilter
    queryset = MonitoringResult.objects.select_related('service', 'service__service_type', 'service__metadata', 'layer',
                                                       'layer__metadata',
                                                       'feature_type', 'feature_type__metadata', 'dataset_metadata',
                                                       'monitoring_run')


class MonitoringResultDetailView(SecuredDetailView):
    model = MonitoringResult
    template_name = 'MrMap/detail_views/table_tab.html'
    queryset = MonitoringResult.objects.all()
    title = _('Details')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        details_table = MonitoringResultDetailTable(data=[self.object, ], request=self.request)
        context.update({'table': details_table})
        return context


class HealthStateTableView(SecuredListMixin, FilterView):
    model = HealthState
    table_class = HealthStateTable
    filterset_class = HealthStateTableFilter
    queryset = HealthState.objects.select_related('service', 'service__service_type', 'service__metadata', 'layer',
                                                  'layer__metadata', 'feature_type', 'feature_type__metadata',
                                                  'dataset_metadata', 'monitoring_run').prefetch_related('reasons')


class HealthStateDetailView(SecuredDetailView):
    model = HealthState
    template_name = 'MrMap/detail_views/table_tab.html'
    queryset = HealthState.objects.all()
    title = _('Details')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        details_table = HealthStateDetailTable(data=[self.object, ], request=self.request)
        context.update({'table': details_table})
        return context
