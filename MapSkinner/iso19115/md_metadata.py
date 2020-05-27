"""
Author: Jonas Kiefer
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: jonas.kiefer@vermkv.rlp.de
Created on: 26.05.20

# ToDo:
"""
from MapSkinner.iso19115.md_data_identification import create_gmd_identification_info
from MapSkinner.iso19115.xml_creation import NS_GMD, create_xml_element, NS_GCO, create_xml_doc
from service.models import Metadata
from structure.models import Contact, Organization


def create_gmd_md_metadata(metadata: Metadata, organization: Organization):
    gmd_contact = create_gmd_contact(organization=organization)
    gmd_date_stamp = ''  # ToDo
    gmd_identification_info = create_gmd_identification_info(metadata)

    gmd_md_metadata = _create_gmd_md_metadata(gmd_contact=[gmd_contact, ],
                                              gmd_date_stamp=gmd_date_stamp,
                                              gmd_identification_info=[gmd_identification_info, ])
    return create_xml_doc(content=gmd_md_metadata)


def _create_gmd_md_metadata(gmd_contact: [str],
                            gmd_date_stamp: str,
                            gmd_identification_info: [str],
                            gmd_file_identifier: str = "",
                            gmd_language: str = "",
                            gmd_character_set: str = "",
                            gmd_parent_identifier: str = "",
                            gmd_hierachy_level: [str] = [],
                            gmd_hierachy_level_name: [str] = [],
                            gmd_metadata_standard_name: str = "",
                            gmd_metadata_standard_version: str = "",
                            gmd_data_set_uri: str = "",
                            gmd_locale: [str] = [],
                            gmd_spatial_representation_info: [str] = [],
                            gmd_reference_system_info: [str] = [],
                            gmd_metadata_extension_info: [str] = [],
                            gmd_content_info: [str] = [],
                            gmd_distribution_info: str = "",
                            gmd_data_quality_info: [str] = [],
                            gmd_portrayal_catalouge_info: [str] = [],
                            gmd_metadata_constraints: [str] = [],
                            gmd_application_schema_info: [str] = [],
                            gmd_metadata_maintenance: str = "", ):
    content = (f"{''.join(str(element) for element in gmd_contact)}"
               f"{gmd_date_stamp}"
               f"{''.join(str(element) for element in gmd_identification_info)}"
               f"{gmd_file_identifier}"
               f"{gmd_language}"
               f"{gmd_character_set}"
               f"{gmd_parent_identifier}"
               f"{''.join(str(element) for element in gmd_hierachy_level)}"
               f"{''.join(str(element) for element in gmd_hierachy_level_name)}"
               f"{gmd_metadata_standard_name}"
               f"{gmd_metadata_standard_version}"
               f"{gmd_data_set_uri}"
               f"{''.join(str(element) for element in gmd_locale)}"
               f"{''.join(str(element) for element in gmd_spatial_representation_info)}"
               f"{''.join(str(element) for element in gmd_reference_system_info)}"
               f"{''.join(str(element) for element in gmd_metadata_extension_info)}"
               f"{''.join(str(element) for element in gmd_content_info)}"
               f"{gmd_distribution_info}"
               f"{''.join(str(element) for element in gmd_data_quality_info)}"
               f"{''.join(str(element) for element in gmd_portrayal_catalouge_info)}"
               f"{''.join(str(element) for element in gmd_metadata_constraints)}"
               f"{''.join(str(element) for element in gmd_application_schema_info)}"
               f"{gmd_metadata_maintenance}"
               )
    attributes = {
        "xmlns:gco": "http://www.isotc211.org/2005/gco",
        "xmlns:gmd": "http://www.isotc211.org/2005/gmd",
        "xmlns:gml": "http://www.opengis.net/gml",
        "xmlns:xlink": "http://www.w3.org/1999/xlink",
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xsi:schemaLocation": "http://www.isotc211.org/2005/gmd http://schemas.opengis.net/iso/19139/20060504/gmd/gmd.xsd",
    }

    return create_xml_element(ns=NS_GMD, tag_name="MD_Metadata", content=content, attributes=attributes)






def create_gmd_contact(organization: Organization):
    """
        ToDo this function should create a gmd:contact xml element from the Mr. Map Contact object and return it as a string
        Best Practices: The organisation directly responsible for the metadata maintenance. Contact information shall be provided.
    """
    gmd_organisation_name = ''  # create_gco_character_string(organization.organization_name)

    gmd_phone = ''  # if organization.phone and organization.facsimile is None \
    # else create_gmd_phone(gmd_ci_telephone=create_gmd_ci_telephone(gmd_voice='' if organization.phone is None else create_gmd_voice(organization.phone),
    #                                                              gmd_facsimile='' if organization.facsimile is None else create_gmd_facsimile(organization.facsimile)))
    gmd_address = ''  # if organization.address or \
    #  organization.city or \
    # organization.postal_code or \
    # organization.country is None else create_gmd_address()

    gmd_online_resource = ''  # create_gmd_online_resource()
    gmd_hours_of_service = ''  # create_gmd_hours_of_service()
    gmd_contact_instructions = ''  # create_gmd_contact_instructions()

    gmd_contact_info = ''  # create_gmd_ci_contact(gmd_phone=gmd_phone)
    gmd_role = ""  # create_gmd_role()

    gmd_ci_responsible_party = create_gmd_ci_responsible_party(gmd_organisation_name=gmd_organisation_name,
                                                               gmd_contact_info=gmd_contact_info,
                                                               gmd_role=gmd_role,
                                                               )
    return create_xml_element(ns=NS_GMD, tag_name="contact", content=gmd_ci_responsible_party)


def create_gmd_ci_contact(gmd_phone: str = "",
                          gmd_address: str = "",
                          gmd_online_resource: str = "",
                          gmd_hours_of_service: str = "",
                          gmd_contact_instructions: str = ""):
    content = f"""{gmd_phone}{gmd_address}{gmd_online_resource}{gmd_hours_of_service}{gmd_contact_instructions}"""
    return create_xml_element(ns=NS_GMD, tag_name="CI_Contact", content=content)


def create_gmd_ci_responsible_party(gmd_role: str,
                                    gmd_individual_name: str = "",
                                    gmd_organisation_name: str = "",
                                    gmd_position_name: str = "",
                                    gmd_contact_info: str = "", ):
    content = f"""{gmd_individual_name}{gmd_organisation_name}{gmd_position_name}{gmd_contact_info}{gmd_role}"""
    return create_xml_element(ns=NS_GMD, tag_name="CI_ResponsibleParty", content=content)


def create_gco_character_string(string: str):
    """
        Mandatory Keywords:
            string: the content of the xml element

        Returns:
            gmd:CharacterString xml element
    """
    return create_xml_element(ns=NS_GCO, tag_name="CharacterString", content=string)
