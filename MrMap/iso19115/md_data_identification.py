"""
Author: Jonas Kiefer
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: jonas.kiefer@vermkv.rlp.de
Created on: 26.05.20

ToDo: description
"""
from MrMap.iso19115.xml_creation import NS_GMD, create_xml_element, create_gco_character_string
from service.models import Metadata


def create_gmd_identification_info(metadata: Metadata):
    gmd_abstract = _create_gmd_abstract(metadata)
    gmd_language = _create_gmd_language(metadata)
    gmd_descriptive_keywords = _create_gmd_descriptive_keywords(metadata)
    gmd_md_data_identification = _create_gmd_md_data_identification(gmd_citation="",  # ToDo
                                                                    gmd_abstract=gmd_abstract,
                                                                    gmd_language=gmd_language,
                                                                    gmd_descriptive_keywords=gmd_descriptive_keywords)
    return create_xml_element(ns=NS_GMD, tag_name="identificationInfo", content=gmd_md_data_identification)


def _create_gmd_md_data_identification(gmd_citation: str,
                                       gmd_abstract: str,
                                       gmd_language: str,
                                       gmd_purpose: str = "",
                                       gmd_credit: str = "",
                                       gmd_status: str = "",
                                       gmd_point_of_contact: str = "",
                                       gmd_resource_maintenance: str = "",
                                       gmd_graphic_overview: str = "",
                                       gmd_resource_format: str = "",
                                       gmd_descriptive_keywords: str = "",
                                       gmd_resource_specific_usage: str = "",
                                       gmd_resource_constraints: str = "",
                                       gmd_aggregation_info: str = "",
                                       gmd_spatial_resolution: str = "",
                                       gmd_character_set: str = "",
                                       gmd_topic_category: str = "",
                                       gmd_environment_description: str = "",
                                       gmd_extent: str = "",
                                       gmd_supplemental_information: str = "",
                                       ):
    content = (f"{gmd_citation}"
               f"{gmd_abstract}"
               f"{gmd_purpose}"
               f"{gmd_language}"
               f"{gmd_credit}"
               f"{gmd_status}"
               f"{gmd_point_of_contact}"
               f"{gmd_resource_maintenance}"
               f"{gmd_graphic_overview}"
               f"{gmd_resource_format}"
               f"{gmd_descriptive_keywords}"
               f"{gmd_resource_specific_usage}"
               f"{gmd_resource_constraints}"
               f"{gmd_aggregation_info}"
               f"{gmd_spatial_resolution}"
               f"{gmd_character_set}"
               f"{gmd_topic_category}"
               f"{gmd_environment_description}"
               f"{gmd_extent}"
               f"{gmd_supplemental_information}")
    return create_xml_element(ns=NS_GMD, tag_name="MD_DataIdentification", content=content, )


def _create_gmd_abstract(metadata: Metadata):
    abstract = create_gco_character_string(metadata.abstract)
    return create_xml_element(ns=NS_GMD, tag_name="abstract", content=abstract)


def _create_gmd_language(metadata: Metadata):
    language = ""

    attributes = {
        "codeList": "http://standards.iso.org/ittf/PubliclyAvailableStandards/ISO_19139_Schemas/resources/codelist/ML_gmxCodelists.xml#LanguageCode",
        "codeListValue": metadata.language_code,
    }
    gmd_language_code = create_xml_element(ns=NS_GMD, tag_name="LanguageCode", content=metadata.language_code,
                                           attributes=attributes)
    gmd_language_element = create_xml_element(ns=NS_GMD, tag_name="language", content=gmd_language_code)
    language += gmd_language_element

    return language


def _create_gmd_descriptive_keywords(metadata: Metadata, as_list: bool = False):
    descriptive_keywords = ""
    descriptive_keywords_list = []
    for keyword in metadata.keywords.all():
        gco_character_string = create_gco_character_string(string=keyword.keyword)
        gmd_md_keywords = _create_gmd_md_keywords(gco_character_string=gco_character_string)
        descriptive_keywords_element = create_xml_element(ns=NS_GMD, tag_name="descriptiveKeywords", content=gmd_md_keywords)
        descriptive_keywords += descriptive_keywords_element
        descriptive_keywords_list.append(descriptive_keywords_element)
    return descriptive_keywords_list if as_list else descriptive_keywords


def _create_gmd_md_keywords(gco_character_string: str,
                            gmd_type: str = "",
                            gmd_thesaurus_name: str = ""
                            ):
    content = (f"{gco_character_string}"
               f"{gmd_type}"
               f"{gmd_thesaurus_name}")
    return create_xml_element(ns=NS_GMD, tag_name="MD_Keywords", content=content, )

