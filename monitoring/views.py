from django.contrib.auth.decorators import login_required
from django.contrib.messages.views import SuccessMessageMixin
from django.utils.decorators import method_decorator
from django.views.generic import CreateView, DetailView
from django_filters.views import FilterView
from MrMap.decorators import permission_required
from MrMap.messages import MONITORING_RUN_SCHEDULED
from MrMap.views import CustomSingleTableMixin, GenericViewContextMixin, InitFormMixin
from monitoring.filters import HealthStateTableFilterForm
from monitoring.forms import MonitoringRunForm
from monitoring.models import MonitoringRun, MonitoringResult, HealthState
from monitoring.tables import MonitoringResultTable, MonitoringRunTable, MonitoringResultDetailTable, HealthStateTable, \
    HealthStateDetailTable
from django.utils.translation import gettext_lazy as _
from structure.permissionEnums import PermissionEnum


@method_decorator(login_required, name='dispatch')
class MonitoringRunTableView(CustomSingleTableMixin, FilterView):
    model = MonitoringRun
    table_class = MonitoringRunTable
    filterset_fields = {'uuid': ['exact'],
                        'start': ['icontains'],
                        'end': ['icontains'],
                        'duration': ['icontains']}


@method_decorator(login_required, name='dispatch')
@method_decorator(permission_required(perm=PermissionEnum.CAN_RUN_MONITORING.value), name='dispatch')
class MonitoringRunNewView(GenericViewContextMixin, InitFormMixin, SuccessMessageMixin, CreateView):
    model = MonitoringRun
    form_class = MonitoringRunForm
    template_name = 'MrMap/detail_views/generic_form.html'
    title = _('New monitoring run')
    success_message = MONITORING_RUN_SCHEDULED


@method_decorator(login_required, name='dispatch')
class MonitoringResultTableView(CustomSingleTableMixin, FilterView):
    model = MonitoringResult
    table_class = MonitoringResultTable
    filterset_fields = {'metadata__title': ['icontains'],
                        'monitoring_run__uuid': ['exact'],
                        'timestamp': ['range'],
                        'error_msg': ['icontains']}


@method_decorator(login_required, name='dispatch')
class MonitoringResultDetailView(GenericViewContextMixin, DetailView):
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


@method_decorator(login_required, name='dispatch')
class HealthStateTableView(CustomSingleTableMixin, FilterView):
    model = HealthState
    table_class = HealthStateTable
    filterset_class = HealthStateTableFilterForm


@method_decorator(login_required, name='dispatch')
class MonitoringResultDetailView(GenericViewContextMixin, DetailView):
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
