"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 27.10.20

"""
from django.http import HttpResponse

from quality.models import ConformityCheckRun, ConformityCheckConfiguration
from quality.quality import Quality
from quality.settings import quality_logger
from service.models import Metadata


# Create your views here.


def check(request, config_id, metadata_id):
    try:
        config = ConformityCheckConfiguration.objects.get(pk=config_id)
        metadata = Metadata.objects.get(pk=metadata_id)
        quality = Quality()
        success = quality.run_check(metadata, config)
        return HttpResponse(f"Success: {success}")
    except ConformityCheckRun.DoesNotExist:
        quality_logger.error("No config or metadata found")
        return HttpResponse("No config or metadata found")
