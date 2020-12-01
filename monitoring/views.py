from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpRequest, HttpResponseRedirect, HttpResponseNotFound
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from MrMap.decorator import check_permission
from MrMap.responses import DefaultContext
from monitoring.filters import HealthReasonFilter
from monitoring.models import MonitoringRun
from monitoring.settings import MONITORING_THRESHOLDS
from monitoring.tables import HealthStateReasonsTable
from monitoring.tasks import run_manual_monitoring
from service.helper.enums import MetadataEnum
from service.models import Metadata
from django.utils.translation import gettext_lazy as _

from structure.models import Permission
from structure.permissionEnums import PermissionEnum
from users.helper import user_helper


@login_required
@check_permission(PermissionEnum.CAN_RUN_MONITORING)
def call_run_monitoring(request: HttpRequest, metadata_id):
    metadata = get_object_or_404(Metadata,
                                 ~Q(metadata_type=MetadataEnum.CATALOGUE.value),
                                 ~Q(metadata_type=MetadataEnum.DATASET.value),
                                 id=metadata_id, )

    run_manual_monitoring.delay(metadatas=[metadata_id, ])
    messages.info(request, _(f"Health check for {metadata} started."))

    return HttpResponseRedirect(reverse(request.GET.get('current-view', 'home')), status=303)


@login_required
def monitoring_results(request: HttpRequest, metadata_id, monitoring_run_id = None, update_params: dict = None, status_code: int = 200,):
    """ Renders a table with all health state messages

        Args:
            request (HttpRequest): The incoming request
            metadata_id: the metadata_id
        Returns:
             A view
        """
    user = user_helper.get_user(request)

    # Default content
    template = "views/health_state.html"
    metadata = get_object_or_404(Metadata, id=metadata_id)
    if monitoring_run_id:
        monitoring_run = get_object_or_404(MonitoringRun, uuid=monitoring_run_id)
        health_state = metadata.get_health_state(monitoring_run=monitoring_run)
    else:
        health_state = metadata.get_health_state()
    if not health_state:
        return HttpResponseNotFound()

    filtered_reasons = HealthReasonFilter(request=request, queryset=health_state.reasons)
    reasons_table = HealthStateReasonsTable(queryset=filtered_reasons.qs,
                                            request=request,
                                            filter_set_class=HealthReasonFilter,
                                            order_by_field='sreasons',  # sreasons = sort reasons
                                            param_lead='reasons-t',
                                            current_view='monitoring:health-state',
                                            )

    last_ten_health_states = metadata.get_health_states()

    params = {
        "reasons_table": reasons_table,
        "health_state": health_state,
        "last_ten_health_states": last_ten_health_states,
        "current_view": "monitoring:health-state",
        "MONITORING_THRESHOLDS": MONITORING_THRESHOLDS,
    }

    if update_params:
        params.update(update_params)

    context = DefaultContext(request, params, user)
    return render(request=request,
                  template_name=template,
                  context=context.get_context(),
                  status=status_code)
