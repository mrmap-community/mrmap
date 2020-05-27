from MapSkinner.iso19115.xml_creation import NS_GMD, create_xml_element, create_gco_character_string
from service.models import Metadata


def create_gmd_identification_info(metadata: Metadata):
    gmd_descriptive_keywords = _create_gmd_descriptive_keywords(metadata)
    gmd_md_data_identification = _create_gmd_md_data_identification(gmd_citation="",  # ToDo
                                                                    gmd_abstract="",  # ToDo
                                                                    gmd_purpose="",  # ToDo
                                                                    gmd_language=[],  # ToDo
                                                                    gmd_descriptive_keywords=gmd_descriptive_keywords)
    return create_xml_element(ns=NS_GMD, tag_name="identificationInfo", content=gmd_md_data_identification)


def _create_gmd_md_data_identification(gmd_citation: str,
                                       gmd_abstract: str,
                                       gmd_purpose: str,
                                       gmd_language: [str],
                                       gmd_credit: [str] = "",
                                       gmd_status: [str] = "",
                                       gmd_point_of_contact: [str] = "",
                                       gmd_resource_maintenance: [str] = "",
                                       gmd_graphic_overview: [str] = "",
                                       gmd_resource_format: [str] = "",
                                       gmd_descriptive_keywords: [str] = "",
                                       gmd_resource_specific_usage: [str] = "",
                                       gmd_resource_constraints: [str] = "",
                                       gmd_aggregation_info: [str] = "",
                                       gmd_spatial_resolution: [str] = "",
                                       gmd_character_set: [str] = "",
                                       gmd_topic_category: [str] = "",
                                       gmd_environment_description: str = "",
                                       gmd_extent: [str] = "",
                                       gmd_supplemental_information: str = "",
                                       ):
    content = (f"{gmd_citation}"
               f"{gmd_abstract}"
               f"{gmd_purpose}"
               f"{''.join(str(element) for element in gmd_language)}"
               f"{''.join(str(element) for element in gmd_credit)}"
               f"{''.join(str(element) for element in gmd_status)}"
               f"{''.join(str(element) for element in gmd_point_of_contact)}"
               f"{''.join(str(element) for element in gmd_resource_maintenance)}"
               f"{''.join(str(element) for element in gmd_graphic_overview)}"
               f"{''.join(str(element) for element in gmd_resource_format)}"
               f"{''.join(str(element) for element in gmd_descriptive_keywords)}"
               f"{''.join(str(element) for element in gmd_resource_specific_usage)}"
               f"{''.join(str(element) for element in gmd_resource_constraints)}"
               f"{''.join(str(element) for element in gmd_aggregation_info)}"
               f"{''.join(str(element) for element in gmd_spatial_resolution)}"
               f"{''.join(str(element) for element in gmd_character_set)}"
               f"{''.join(str(element) for element in gmd_topic_category)}"
               f"{gmd_environment_description}"
               f"{''.join(str(element) for element in gmd_extent)}"
               f"{gmd_supplemental_information}"
               )

    return create_xml_element(ns=NS_GMD, tag_name="MD_DataIdentification", content=content, )


def _create_gmd_descriptive_keywords(metadata: Metadata):
    descriptive_keywords = ""
    for keyword in metadata.keywords.all():
        gmd_keyword = _create_gmd_keyword(keyword.keyword)
        gmd_md_keywords = _create_gmd_md_keywords(gmd_keyword=gmd_keyword)
        descriptive_keywords += create_xml_element(ns=NS_GMD, tag_name="descriptiveKeywords", content=gmd_md_keywords)
    return descriptive_keywords


def _create_gmd_md_keywords(gmd_keyword: [str],
                            gmd_type: str = "",
                            gmd_thesaurus_name: str = ""
                            ):
    content = (f"{''.join(str(element) for element in gmd_keyword)}"
               f"{gmd_type}"
               f"{gmd_thesaurus_name}"
               )

    return create_xml_element(ns=NS_GMD, tag_name="MD_Keywords", content=content, )


def _create_gmd_keyword(keyword: str):
    return create_gco_character_string(string=keyword)
