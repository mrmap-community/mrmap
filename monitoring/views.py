from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from MrMap.decorator import check_permission
from MrMap.responses import DefaultContext
from monitoring.tables import WarningReasonsTable, CriticalReasonsTable
from monitoring.tasks import run_manual_monitoring
from service.helper.enums import MetadataEnum
from service.models import Metadata
from django.utils.translation import gettext_lazy as _

from structure.models import Permission
from users.helper import user_helper


@login_required
@check_permission(Permission(can_run_monitoring=True))
def call_run_monitoring(request: HttpRequest, metadata_id):
    metadata = get_object_or_404(Metadata,
                                 ~Q(metadata_type=MetadataEnum.CATALOGUE.value),
                                 ~Q(metadata_type=MetadataEnum.DATASET.value),
                                 id=metadata_id, )

    run_manual_monitoring.delay(metadatas=[metadata_id, ])
    messages.info(request, _(f"Health check for {metadata} started."))

    return HttpResponseRedirect(reverse(request.GET.get('current-view') or reverse('home'),), status=303)


@login_required
def monitoring_results(request: HttpRequest, metadata_id, update_params: dict = None, status_code: int = 200,):
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

    healt_state = metadata.get_health_state()

    warning_reasons_table = WarningReasonsTable(data=healt_state.warning_reasons,
                                                orderable=False,
                                                request=request,
                                                current_view='monitoring:health-state',)

    critical_reasons_table = CriticalReasonsTable(data=healt_state.critical_reasons,
                                                  orderable=False,
                                                  request=request,
                                                  current_view='monitoring:health-state',)
    params = {
        "warning_reasons": warning_reasons_table,
        "critical_reasons": critical_reasons_table,
        "current_view": "monitoring:health-state",
    }

    if update_params:
        params.update(update_params)

    context = DefaultContext(request, params, user)
    return render(request=request,
                  template_name=template,
                  context=context.get_context(),
                  status=status_code)