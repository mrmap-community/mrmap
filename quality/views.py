"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 27.10.20

"""
from django.db.models import Model
from django.http import HttpResponse
from django.shortcuts import render

# Create your views here.
from quality.models import ConformityCheckRun
from quality.quality import Quality
from quality.settings import quality_logger


def check(request, run_id):
    try:
        check_run = ConformityCheckRun.objects.get(id=run_id)
        quality = Quality()
        quality.run_check(check_run)
        return HttpResponse("Hello world")
    except ConformityCheckRun.DoesNotExist:
        quality_logger.error(f"No model found for id {run_id}")
        return HttpResponse("Failed")
