"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 15.07.20

"""
from celery import shared_task
from django.db import transaction, IntegrityError

from MrMap.settings import GENERIC_NAMESPACE_TEMPLATE
from csw.settings import csw_logger, CSW_GENERIC_ERROR_TEMPLATE
from csw.utils.harvester import Harvester
from service.helper import xml_helper
from service.helper.enums import MetadataEnum
from service.models import Metadata
from structure.models import MrMapGroup


@shared_task(name="async_create_metadata_from_md_metadata")
@transaction.atomic
def async_create_metadata_from_md_metadata(response: str, harvesting_group_id: int):
    from csw.utils.harvester import Harvester
    xml_response = xml_helper.parse_xml(response)
    md_metadata_entries = xml_helper.try_get_element_from_xml(
        "//" + GENERIC_NAMESPACE_TEMPLATE.format("MD_Metadata"),
        xml_response
    )
    harvesting_group = MrMapGroup.objects.get(
        id=harvesting_group_id
    )
    Harvester._create_metadata_from_md_metadata(md_metadata_entries, harvesting_group)


@shared_task(name="async_harvest")
def async_harvest(catalogue_metadata_id: int, harvesting_group_id: int):
    md = Metadata.objects.get(
        id=catalogue_metadata_id,
        metadata_type=MetadataEnum.CATALOGUE.value
    )
    harvesting_group = MrMapGroup.objects.get(
        id=harvesting_group_id
    )
    try:
        harvester = Harvester(md, harvesting_group, max_records_per_request=1000)
        harvester.harvest()

    except IntegrityError as e:
        csw_logger.error(
            CSW_GENERIC_ERROR_TEMPLATE.format(
                md.title,
                e
            )
        )