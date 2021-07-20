"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 15.07.20

"""
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
from django.conf import settings

from csw.models import HarvestResult
from csw.settings import CSW_GENERIC_ERROR_TEMPLATE
from csw.utils.harvester import Harvester
from celery import shared_task

from main.tasks import default_task_handler


@shared_task(name='async_harvest')
def async_harvest(owned_by_org: str, harvest_result_id: int, **kwargs):
    """ Performs the harvesting procedure in a background celery task

    Args:
        harvest_result_id (int):
    Returns:

    """
    default_task_handler(**kwargs)

    try:
        harvest_result = HarvestResult.objects \
            .select_related('metadata') \
            .get(pk=harvest_result_id)
        try:
            harvester = Harvester(harvest_result,
                                  max_records_per_request=500)
            harvester.harvest()

            return {'msg': 'Done. Catalogue harvested successful.',
                    'id': str(harvest_result.metadata.pk),
                    'absolute_url': harvest_result.metadata.get_absolute_url(),
                    'absolute_url_html': f'<a href={harvest_result.metadata.get_absolute_url()}>{harvest_result.metadata.title}</a>'}

        except IntegrityError as e:
            settings.ROOT_LOGGER.error(
                CSW_GENERIC_ERROR_TEMPLATE.format(
                    harvest_result.metadata.title,
                    e
                )
            )
    except ObjectDoesNotExist:
        # todo: logging
        pass
