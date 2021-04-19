"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 27.10.20

"""
import json

from celery import current_task, states
from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from rest_framework import status

from quality.models import ConformityCheckRun
from quality.tasks import run_quality_check, complete_validation, \
    complete_validation_error
from service.models import Metadata
from structure.permissionEnums import PermissionEnum

CURRENT_VIEW_QUERY_Param = 'current-view'
CURRENT_VIEW_ARG_QUERY_Param = 'current-view-arg'


@login_required
@permission_required(
    PermissionEnum.CAN_RUN_VALIDATION,
    raise_exception=True,
)
def validate(request, metadata_id: str):
    config_id = request.GET.get('config_id', None)
    current_view = request.GET.get(CURRENT_VIEW_QUERY_Param, None)
    current_view_arg = request.GET.get(CURRENT_VIEW_ARG_QUERY_Param, None)

    if config_id is None:
        return HttpResponse('Parameter config_id is missing',
                            status=status.HTTP_400_BAD_REQUEST)
    metadata = get_object_or_404(Metadata, pk=metadata_id)

    if not metadata.is_active:
        return HttpResponse('Resource to be validated is not active',
                            status=status.HTTP_400_BAD_REQUEST)

    user = request.user
    owned_by_org = metadata.owned_by_org

    success_callback = complete_validation.s()
    error_callback = complete_validation_error.s(user_id=user.id,
                                                 config_id=config_id,
                                                 metadata_id=metadata.id)

    pending_task = run_quality_check.apply_async(args=(config_id, metadata_id),
                                                 link=success_callback,
                                                 link_error=error_callback)

    if current_task:
        current_task.update_state(
            state=states.STARTED,
            meta={
                "current": 10,
                "phase": f"Validating {metadata.title}",
            }
        )

    if current_view is not None:
        if current_view_arg is not None:
            return HttpResponseRedirect(
                reverse(current_view, args=(current_view_arg,)), status=303)
        else:
            return HttpResponseRedirect(reverse(current_view), status=303)

    return HttpResponse(status=status.HTTP_200_OK)


def get_latest(request, metadata_id: str):
    metadata = get_object_or_404(Metadata, pk=metadata_id)

    try:
        latest_run = ConformityCheckRun.objects.get_latest_check(metadata)
        latest = {
            "passed": latest_run.passed,
            "running": latest_run.is_running(),
        }
    except ConformityCheckRun.DoesNotExist:
        latest = {
            "passed": None,
            "running": None,
        }

    return JsonResponse(latest)
