"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 27.10.20

"""

from django.http import HttpResponse
# Create your views here.
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response

import quality.quality as quality
from quality import tasks
from quality.models import ConformityCheckConfigurationInternal
from quality.models import ConformityCheckRun, ConformityCheckConfiguration
from quality.settings import quality_logger
from service.helper.enums import PendingTaskEnum
from service.models import Metadata


# Create your views here.
from structure.models import PendingTask
from users.helper import user_helper


def validate(request, metadata_id: str):
    config_id = request.GET.get('config_id', None)
    if config_id is None:
        return Response('Parameter config_id is missing',
                        status=status.HTTP_400_BAD_REQUEST)
    metadata = get_object_or_404(Metadata, pk=metadata_id)
    config = get_object_or_404(ConformityCheckConfiguration, pk=config_id)
    #tasks.run_check.delay(metadata, config)



    user = user_helper.get_user(request)
    group = metadata.created_by

    pending_task = tasks.my_task.delay(user.id, group.id)
    # pending_task = tasks.my_task(user, group)


    # return pending_task_db



    return HttpResponse(status=status.HTTP_200_OK)


def check(request, config_id, metadata_id):
    try:
        config = ConformityCheckConfiguration.objects.get(pk=config_id)
        metadata = Metadata.objects.get(pk=metadata_id)
        success = quality.run_check(metadata, config)
        return HttpResponse(f"Success: {success}")
    except ConformityCheckRun.DoesNotExist:
        quality_logger.error("No config or metadata found")
        return HttpResponse("No config or metadata found")


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

