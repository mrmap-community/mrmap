from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Q
from django.http import HttpRequest, HttpResponseRedirect, HttpResponseNotFound
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import CreateView
from django_bootstrap_swt.components import Tag
from django_filters.views import FilterView

from MrMap.decorators import permission_required
from MrMap.icons import IconEnum
from MrMap.messages import GROUP_SUCCESSFULLY_CREATED, MONITORING_RUN_SCHEDULED
from MrMap.views import CustomSingleTableMixin, GenericViewContextMixin, InitFormMixin
from monitoring.filters import HealthReasonFilter
from monitoring.forms import MonitoringRunForm
from monitoring.models import MonitoringRun, HealthState, MonitoringResult
from monitoring.settings import MONITORING_THRESHOLDS
from monitoring.tables import HealthStateTable, MonitoringResultTable, MonitoringRunTable
from service.helper.enums import MetadataEnum
from service.models import Metadata
from django.utils.translation import gettext_lazy as _

from structure.models import Permission
from structure.permissionEnums import PermissionEnum
from users.helper import user_helper


@method_decorator(login_required, name='dispatch')
class MonitoringRunTableView(CustomSingleTableMixin, FilterView):
    model = MonitoringRun
    table_class = MonitoringRunTable
    filterset_fields = {'uuid': ['exact'],
                        'start': ['icontains'],
                        'end': ['icontains'],
                        'duration': ['icontains']}
    title = _('Monitoring runs').__str__()


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
                        'timestamp': ['range'],
                        'error_msg': ['icontains']}
    title = _('Monitoring results').__str__()
