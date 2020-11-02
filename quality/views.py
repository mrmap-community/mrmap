"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 27.10.20

"""
from django.db.models import Model
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404

# Create your views here.
from quality.models import ConformityCheckRun, ConformityCheckConfigurationInternal
from quality.quality import Quality
from quality.settings import quality_logger
from service.models import Metadata


def check(request, run_id):
    try:
        check_run = ConformityCheckRun.objects.get(id=run_id)
        quality = Quality()
        quality.run_check(check_run)
        return HttpResponse("Hello world")
    except ConformityCheckRun.DoesNotExist:
        quality_logger.error(f"No model found for id {run_id}")
        return HttpResponse("Failed")


def check_internal(request, metadata_id, config_id):
    try:
        metadata = Metadata.objects.get(pk=metadata_id)
        config = ConformityCheckConfigurationInternal.objects.get(pk=config_id)

        quality = Quality(metadata, config)

        # TODO use this method on production
        # if quality.has_running_check():
        #     raise Exception(f"Metadata validation for {metadata_id} already running. Skipping.")

        quality.run_check()
        return HttpResponse("Hello world")
    except Metadata.DoesNotExist:
        quality_logger.error(f"No metadata found for id {metadata_id}")
        # TODO remove this
        return HttpResponse("Failed")
    except ConformityCheckConfigurationInternal.DoesNotExist:
        quality_logger.error(f"No configuration found for id {config_id}")
        # TODO remove this
        return HttpResponse("Failed")
