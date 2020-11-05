"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 27.10.20

"""
import json

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from rest_framework import status

import quality.quality as quality
from MrMap.decorator import check_permission
from quality.models import ConformityCheckConfigurationInternal
from quality.models import ConformityCheckRun, ConformityCheckConfiguration
from quality.settings import quality_logger
from quality.tasks import run_quality_check, complete_validation, \
    complete_validation_error
from service.helper.enums import PendingTaskEnum
from service.models import Metadata
from structure.models import PendingTask
from structure.permissionEnums import PermissionEnum
from users.helper import user_helper

CURRENT_VIEW_QUERY_Param = 'current-view'
CURRENT_VIEW_ARG_QUERY_Param = 'current-view-arg'


@login_required
@check_permission(
    PermissionEnum.CAN_RUN_VALIDATION
)
def validate(request, metadata_id: str):
    config_id = request.GET.get('config_id', None)
    current_view = request.GET.get(CURRENT_VIEW_QUERY_Param, None)
    current_view_arg = request.GET.get(CURRENT_VIEW_ARG_QUERY_Param, None)

    if config_id is None:
        return HttpResponse('Parameter config_id is missing',
                            status=status.HTTP_400_BAD_REQUEST)
    metadata = get_object_or_404(Metadata, pk=metadata_id)

    user = user_helper.get_user(request)
    group = metadata.created_by

    success_callback = complete_validation.s(group_id=group.id, user_id=user.id)
    error_callback = complete_validation_error.s(group_id=group.id,
                                                 user_id=user.id,
                                                 config_id=config_id,
                                                 metadata_id=metadata.id)

    pending_task = run_quality_check.s(config_id, metadata_id).set(
        link=success_callback, link_error=error_callback).delay()

    pending_task_db = PendingTask()
    pending_task_db.created_by = group
    pending_task_db.task_id = pending_task.id
    pending_task_db.description = json.dumps({
        "status": f'Validating {metadata.title}',
        "service": metadata.title,
        "phase": "Validating",
    })
    pending_task_db.type = PendingTaskEnum.VALIDATE.value
    pending_task_db.save()

    if current_view is not None:
        if current_view_arg is not None:
            return HttpResponseRedirect(
                reverse(current_view, args=(current_view_arg,)), status=303)
        else:
            return HttpResponseRedirect(reverse(current_view), status=303)

    return HttpResponse(status=status.HTTP_200_OK)


def check(request, config_id, metadata_id):
    num_running = ConformityCheckRun.objects.filter(metadata=metadata_id,
                                                    time_stop__exact=None).count()
    if num_running > 0:
        return HttpResponse(f"Check for metadata {metadata_id} still running")
    #    run_quality_check(config_id, metadata_id)
    run_quality_check.delay(config_id, metadata_id)
    return HttpResponse(
        f"Started quality check for config {config_id} and metadata "
        f"{metadata_id}")


def check_internal(request, metadata_id, config_id):
    try:
        metadata = Metadata.objects.get(pk=metadata_id)
        config = ConformityCheckConfigurationInternal.objects.get(pk=config_id)
        quality.run_check(metadata, config)
        return HttpResponse("Hello world")
    except Metadata.DoesNotExist:
        quality_logger.error(f"No metadata found for id {metadata_id}")
        # TODO remove this
        return HttpResponse("Failed")
    except ConformityCheckConfigurationInternal.DoesNotExist:
        quality_logger.error(f"No configuration found for id {config_id}")
        # TODO remove this
        return HttpResponse("Failed")


def new_check(request, metadata_id, config_id):
    metadata = Metadata.objects.get(pk=metadata_id)
    config = ConformityCheckConfiguration.objects.get(id=config_id)
    quality.run_check(metadata, config)
    return HttpResponse("success")


def get_configs_for(request, metadata_type: str):
    configs = ConformityCheckConfiguration.objects.get_for_metadata_type(
        metadata_type)
    return HttpResponse(configs)
