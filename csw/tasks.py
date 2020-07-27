"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 15.07.20

"""
from celery import shared_task
from django.db import IntegrityError

from csw.settings import csw_logger, CSW_GENERIC_ERROR_TEMPLATE
from csw.utils.harvester import Harvester
from service.helper.enums import MetadataEnum
from service.models import Metadata
from structure.models import MrMapGroup


@shared_task(name="async_harvest")
def async_harvest(catalogue_metadata_id: int, harvesting_group_id: int):
    """ Performs the harvesting procedure in a background celery task

    Args:
        catalogue_metadata_id (int):
        harvesting_group_id (int):
    Returns:

    """
    md = Metadata.objects.get(
        id=catalogue_metadata_id,
        metadata_type=MetadataEnum.CATALOGUE.value
    )
    harvesting_group = MrMapGroup.objects.get(
        id=harvesting_group_id
    )
    try:
        harvester = Harvester(md, harvesting_group, max_records_per_request=1000)
        harvester.harvest(task_id=async_harvest.request.id)

    except IntegrityError as e:
        csw_logger.error(
            CSW_GENERIC_ERROR_TEMPLATE.format(
                md.title,
                e
            )
        )