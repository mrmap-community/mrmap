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
    xml_response = xml_helper.parse_xml(response)
    md_metadata_entries = xml_helper.try_get_element_from_xml(
        "//" + GENERIC_NAMESPACE_TEMPLATE.format("MD_Metadata"),
        xml_response
    )
    harvesting_group = MrMapGroup.objects.get(
        id=harvesting_group_id
    )
    for md_metadata in md_metadata_entries:
        _id = xml_helper.try_get_text_from_xml_element(
            md_metadata,
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("fileIdentifier")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
        )
        metadata = Metadata.objects.get_or_create(
            id=_id,
            identifier=_id,
        )[0]
        metadata.created_by = harvesting_group
        metadata.origin = ResourceOriginEnum.CATALOGUE.value
        metadata.title = xml_helper.try_get_text_from_xml_element(
            md_metadata,
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("MD_DataIdentification")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("citation")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CI_Citation")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("title")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
        )
        metadata.language_code = xml_helper.try_get_text_from_xml_element(
            md_metadata,
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("language")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("LanguageCode")
        )
        hierarchy_level = xml_helper.try_get_text_from_xml_element(
            md_metadata,
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("hierarchyLevel")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("MD_ScopeCode")
        )
        metadata.metadata_type = hierarchy_level
        metadata.abstract = xml_helper.try_get_text_from_xml_element(
            md_metadata,
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("abstract")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
        )
        keywords = xml_helper.try_get_element_from_xml(
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("keyword")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString"),
            md_metadata,
        ) or []
        keywords = [
            Keyword.objects.get_or_create(
                keyword=xml_helper.try_get_text_from_xml_element(kw)
            )[0]
            for kw in keywords
        ]
        metadata.keywords.add(*keywords)
        metadata.access_constraints = xml_helper.try_get_text_from_xml_element(
            md_metadata,
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("otherConstraints")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
        )
        categories = xml_helper.try_get_element_from_xml(
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("MD_TopicCategoryCode"),
            md_metadata,
        ) or []
        for cat in categories:
            cat_obj = Category.objects.filter(
                title_EN=xml_helper.try_get_text_from_xml_element(cat)
            ).first()
            if cat_obj is not None:
                metadata.categories.add(cat_obj)

        extent = [
            xml_helper.try_get_text_from_xml_element(
                md_metadata,
                ".//" + GENERIC_NAMESPACE_TEMPLATE.format("westBoundLongitude")
                + "/" + GENERIC_NAMESPACE_TEMPLATE.format("Decimal")
            ),
            xml_helper.try_get_text_from_xml_element(
                md_metadata,
                ".//" + GENERIC_NAMESPACE_TEMPLATE.format("southBoundLatitude")
                + "/" + GENERIC_NAMESPACE_TEMPLATE.format("Decimal")
            ),
            xml_helper.try_get_text_from_xml_element(
                md_metadata,
                ".//" + GENERIC_NAMESPACE_TEMPLATE.format("eastBoundLongitude")
                + "/" + GENERIC_NAMESPACE_TEMPLATE.format("Decimal")
            ),
            xml_helper.try_get_text_from_xml_element(
                md_metadata,
                ".//" + GENERIC_NAMESPACE_TEMPLATE.format("northBoundLatitude")
                + "/" + GENERIC_NAMESPACE_TEMPLATE.format("Decimal")
            ),
        ]
        metadata.bounding_geometry = GEOSGeometry(Polygon.from_bbox(bbox=extent), srid=DEFAULT_SRS)
        metadata.metadata_type = hierarchy_level
        metadata.save()

        # Load non-metadata data
        described_resource = None
        if hierarchy_level == MetadataEnum.DATASET.value:
            described_resource = _create_dataset_from_md_metadata(md_metadata, metadata)
            described_resource.metadata = metadata
            described_resource.save()


def _create_dataset_from_md_metadata(md_metadata: Element, metadata: Metadata) -> Dataset:
    """ Creates a Dataset record from xml data

    Args:
        md_metadata (Element): The xml element which holds the data
        metadata (Metadata): The related metadata element
    Returns:

    """
    described_resource = Dataset()
    described_resource.language_code = metadata.language_code
    described_resource.language_code_list_url = xml_helper.try_get_attribute_from_xml_element(
        md_metadata,
        "codeList",
        ".//" + GENERIC_NAMESPACE_TEMPLATE.format("language")
        + "/" + GENERIC_NAMESPACE_TEMPLATE.format("LanguageCode")
    )
    described_resource.character_set_code = xml_helper.try_get_text_from_xml_element(
        md_metadata,
        ".//" + GENERIC_NAMESPACE_TEMPLATE.format("characterSet")
        + "/" + GENERIC_NAMESPACE_TEMPLATE.format("MD_CharacterSetCode")
    )
    described_resource.character_set_code_list_url = xml_helper.try_get_attribute_from_xml_element(
        md_metadata,
        "codeList",
        ".//" + GENERIC_NAMESPACE_TEMPLATE.format("characterSet")
        + "/" + GENERIC_NAMESPACE_TEMPLATE.format("MD_CharacterSetCode")
    )
    described_resource.date_stamp = xml_helper.try_get_text_from_xml_element(
        md_metadata,
        ".//" + GENERIC_NAMESPACE_TEMPLATE.format("dateStamp")
        + "/" + GENERIC_NAMESPACE_TEMPLATE.format("Date")
    )
    described_resource.metadata_standard_name = xml_helper.try_get_text_from_xml_element(
        md_metadata,
        ".//" + GENERIC_NAMESPACE_TEMPLATE.format("metadataStandardName")
        + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
    )
    described_resource.metadata_standard_version = xml_helper.try_get_text_from_xml_element(
        md_metadata,
        ".//" + GENERIC_NAMESPACE_TEMPLATE.format("metadataStandardVersion")
        + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
    )
    described_resource.update_frequency_code = xml_helper.try_get_text_from_xml_element(
        md_metadata,
        ".//" + GENERIC_NAMESPACE_TEMPLATE.format("MD_MaintenanceFrequencyCode")
    )
    described_resource.update_frequency_code_list_url = xml_helper.try_get_attribute_from_xml_element(
        md_metadata,
        "codeList",
        ".//" + GENERIC_NAMESPACE_TEMPLATE.format("MD_MaintenanceFrequencyCode")
    )
    described_resource.use_limitation = xml_helper.try_get_text_from_xml_element(
        md_metadata,
        ".//" + GENERIC_NAMESPACE_TEMPLATE.format("useLimitation")
        + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
    )
    described_resource.lineage_statement = xml_helper.try_get_text_from_xml_element(
        md_metadata,
        ".//" + GENERIC_NAMESPACE_TEMPLATE.format("statement")
        + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
    )
    return described_resource