"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 15.07.20

"""
from celery import shared_task
from django.contrib.gis.geos import GEOSGeometry, Polygon
from django.db import transaction
from lxml.etree import Element

from MrMap.settings import GENERIC_NAMESPACE_TEMPLATE
from service.helper import xml_helper
from service.helper.enums import MetadataEnum, ResourceOriginEnum
from service.models import Dataset, Metadata, Keyword, Category
from service.settings import DEFAULT_SRS
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
    Harvester._multithread_create_metadata_from_md_metadata(md_metadata_entries, harvesting_group)