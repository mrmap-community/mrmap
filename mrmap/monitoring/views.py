from django.urls import reverse_lazy
from django_filters.views import FilterView
from MrMap.messages import MONITORING_RUN_SCHEDULED, NO_PERMISSION
from main.views import SecuredListMixin, SecuredCreateView, SecuredDetailView
from monitoring.filters import HealthStateTableFilter, MonitoringResultTableFilter, MonitoringRunTableFilter
from monitoring.forms import MonitoringRunForm
from monitoring.models import MonitoringRun, MonitoringResult, HealthState
from monitoring.tables import MonitoringResultTable, MonitoringRunTable, MonitoringResultDetailTable, HealthStateTable, \
    HealthStateDetailTable
from django.utils.translation import gettext_lazy as _

from structure.permissionEnums import PermissionEnum


class MonitoringRunTableView(SecuredListMixin, FilterView):
    model = MonitoringRun
    table_class = MonitoringRunTable
    filterset_class = MonitoringRunTableFilter


class MonitoringRunNewView(SecuredCreateView):
    model = MonitoringRun
    form_class = MonitoringRunForm
    template_name = 'MrMap/detail_views/generic_form.html'
    title = _('New monitoring run')
    success_message = MONITORING_RUN_SCHEDULED
    permission_required = PermissionEnum.CAN_ADD_MONITORING_RUN.value
    raise_exception = True
    permission_denied_message = NO_PERMISSION
    success_url = reverse_lazy('resource:pending-tasks')


class MonitoringResultTableView(SecuredListMixin, FilterView):
    model = MonitoringResult
    table_class = MonitoringResultTable
    filterset_class = MonitoringResultTableFilter


class MonitoringResultDetailView(SecuredDetailView):
    # todo: check if we need this
    class Meta:
        verbose_name = _('Details')

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


class HealthStateDetailView(SecuredDetailView):
    # todo check if we need this
    class Meta:
        verbose_name = _('Details')

    model = HealthState
    template_name = 'MrMap/detail_views/table_tab.html'
    queryset = HealthState.objects.all()
    title = _('Details')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        details_table = HealthStateDetailTable(data=[self.object, ], request=self.request)
        context.update({'table': details_table})
        return context
