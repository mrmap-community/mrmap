"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 15.07.20

"""
from celery import shared_task
<<<<<<< HEAD
from django.conf import settings
from django.contrib.auth import get_user_model
=======
from celery.exceptions import Reject
from django.core.exceptions import ObjectDoesNotExist
>>>>>>> 6547e7f6ad710c8351a3ede267a054c17a44fa14
from django.db import IntegrityError
from django_celery_results.models import TaskResult

from csw.models import HarvestResult
from csw.settings import csw_logger, CSW_GENERIC_ERROR_TEMPLATE
from csw.utils.harvester import Harvester
from service.helper.enums import MetadataEnum
from service.models import Metadata
from structure.models import Organization


@shared_task(name="async_harvest")
<<<<<<< HEAD
def async_harvest(catalogue_metadata_id, user_id, harvesting_organization_id):
    """ Performs the harvesting procedure in a background celery task

    Args:
        catalogue_metadata_id:
        harvesting_organization_id:
    Returns:

    """
    md = Metadata.objects.get(
        pk=catalogue_metadata_id,
        metadata_type=MetadataEnum.CATALOGUE.value
    )
    harvesting_organization = Organization.objects.get(
        pk=harvesting_organization_id
    )
    user = get_user_model().objects.get(pk=user_id)
    try:
        harvester = Harvester(md, user, harvesting_organization, max_records_per_request=1000)
        harvester.harvest(task_id=async_harvest.request.id)

    except IntegrityError as e:
        csw_logger.error(
            CSW_GENERIC_ERROR_TEMPLATE.format(
                md.title,
                e
=======
def async_harvest(harvest_result_id: int):
    """ Performs the harvesting procedure in a background celery task

    Args:
        harvest_result_id (int):
    Returns:

    """
    try:
        harvest_result = HarvestResult.objects\
            .select_related('metadata',
                            'metadata__service__created_by__mrmapgroup')\
            .get(pk=harvest_result_id)
        try:
            harvester = Harvester(harvest_result,
                                  max_records_per_request=1000)
            harvester.harvest()

        except IntegrityError as e:
            csw_logger.error(
                CSW_GENERIC_ERROR_TEMPLATE.format(
                    harvest_result.metadata.title,
                    e
                )
>>>>>>> 6547e7f6ad710c8351a3ede267a054c17a44fa14
            )
    except ObjectDoesNotExist:
        # todo: logging
        pass

