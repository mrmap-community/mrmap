"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 15.07.20

"""
from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from csw.settings import csw_logger, CSW_GENERIC_ERROR_TEMPLATE
from csw.utils.harvester import Harvester
from service.helper.enums import MetadataEnum
from service.models import Metadata
from structure.models import Organization


@shared_task(name="async_harvest")
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
            )
        )