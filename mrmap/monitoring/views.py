from django.contrib.auth.decorators import login_required
from django.contrib.messages.views import SuccessMessageMixin
from django.utils.decorators import method_decorator
from django.views.generic import CreateView, DetailView
from django_filters.views import FilterView
from guardian.mixins import LoginRequiredMixin, PermissionRequiredMixin, PermissionListMixin

from MrMap.messages import MONITORING_RUN_SCHEDULED, NO_PERMISSION
from MrMap.views import CustomSingleTableMixin, GenericViewContextMixin, InitFormMixin
from monitoring.filters import HealthStateTableFilter, MonitoringResultTableFilter, MonitoringRunTableFilter
from monitoring.forms import MonitoringRunForm
from monitoring.models import MonitoringRun, MonitoringResult, HealthState
from monitoring.tables import MonitoringResultTable, MonitoringRunTable, MonitoringResultDetailTable, HealthStateTable, \
    HealthStateDetailTable
from django.utils.translation import gettext_lazy as _
from structure.permissionEnums import PermissionEnum


class MonitoringRunTableView(LoginRequiredMixin, PermissionListMixin, CustomSingleTableMixin, FilterView):
    model = MonitoringRun
    table_class = MonitoringRunTable
    filterset_class = MonitoringRunTableFilter
    permission_required = [PermissionEnum.CAN_VIEW_MONITORING_RUN.value]


class MonitoringRunNewView(LoginRequiredMixin, PermissionRequiredMixin, GenericViewContextMixin, InitFormMixin, SuccessMessageMixin, CreateView):
    model = MonitoringRun
    form_class = MonitoringRunForm
    template_name = 'MrMap/detail_views/generic_form.html'
    title = _('New monitoring run')
    success_message = MONITORING_RUN_SCHEDULED
    permission_required = [PermissionEnum.CAN_RUN_MONITORING.value]
    raise_exception = True
    permission_denied_message = NO_PERMISSION


class MonitoringResultTableView(LoginRequiredMixin, PermissionListMixin, CustomSingleTableMixin, FilterView):
    model = MonitoringResult
    table_class = MonitoringResultTable
    filterset_class = MonitoringResultTableFilter
    permission_required = [PermissionEnum.CAN_VIEW_MONITORING_RESULT.value]


@method_decorator(login_required, name='dispatch')
class MonitoringResultDetailView(LoginRequiredMixin, PermissionRequiredMixin, GenericViewContextMixin, DetailView):
    class Meta:
        verbose_name = _('Details')

    model = MonitoringResult
    template_name = 'MrMap/detail_views/table_tab.html'
    queryset = MonitoringResult.objects.all()
    title = _('Details')
    permission_required = [PermissionEnum.CAN_VIEW_MONITORING_RESULT.value]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        details_table = MonitoringResultDetailTable(data=[self.object, ], request=self.request)
        context.update({'table': details_table})
        return context


@method_decorator(login_required, name='dispatch')
class HealthStateTableView(LoginRequiredMixin, PermissionListMixin, CustomSingleTableMixin, FilterView):
    model = HealthState
    table_class = HealthStateTable
    filterset_class = HealthStateTableFilter
    permission_required = [PermissionEnum.CAN_VIEW_HEALTH_STATE.value]


@method_decorator(login_required, name='dispatch')
class HealthStateDetailView(LoginRequiredMixin, PermissionRequiredMixin, GenericViewContextMixin, DetailView):
    class Meta:
        verbose_name = _('Details')

    model = HealthState
    template_name = 'MrMap/detail_views/table_tab.html'
    queryset = HealthState.objects.all()
    title = _('Details')
    permission_required = [PermissionEnum.CAN_VIEW_HEALTH_STATE.value]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        details_table = HealthStateDetailTable(data=[self.object, ], request=self.request)
        context.update({'table': details_table})
        return context
