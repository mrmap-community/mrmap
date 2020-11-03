"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 27.10.20

"""

from django.http import HttpResponse

# Create your views here.
from quality.models import ConformityCheckConfigurationInternal
from quality.models import ConformityCheckRun, ConformityCheckConfiguration
from quality.settings import quality_logger
from service.models import Metadata
import quality.quality as quality


# Create your views here.


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
