"""
Author: Jonas Kiefer
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: jonas.kiefer@vermkv.rlp.de
Created on: 19.05.20

This file defines some xml skeletons for the ISO 19115 standard for now.
"""



# ToDo:
"""
<gmd:address>
<gmd:CI_Address>
    <gmd:electronicMailAddress>
        <gco:CharacterString>gabriele.schaub@bad-neuenahr-ahrweiler.de</gco:CharacterString>
    </gmd:electronicMailAddress>
</gmd:CI_Address>
</gmd:address>
"""



def create_gco_character_string(string: str):
    """
        Mandatory Keywords:
            string: the content of the xml element

        Returns:
            gmd:CharacterString xml element
    """
    return create_xml_element(ns=NS_GCO, tag_name="CharacterString", content=string)


def create_gmd_date(content: str):
    """
        Mandatory Keywords:
            content: the content of the xml element

        Returns:
            gmd:date xml element
    """
    return create_xml_element(ns=NS_GMD, tag_name="date", content=content)


def create_gmd_ci_datetypecode(date_type_code: str):
    """
        Mandatory Keywords:
            date_type_code: the CI_DateTypeCode value

        Returns:
            gmd:CI_DateTypeCode xml element
    """
    attributes = {
        "codeList": "http://standards.iso.org/ittf/PubliclyAvailableStandards/ISO_19139_Schemas/resources/codelist/ML_gmxCodelists.xml#CI_DateTypeCode",
        "codeListValue": date_type_code
    }
    return create_xml_element(ns=NS_GMD, tag_name="CI_DateTypeCode", content=date_type_code, attributes=attributes)


def create_gmd_ci_date(date: str, date_type_code: str):
    """
        Mandatory Keywords:
            date: the date value as YYYY-MM-DD formated
            date_type_code: the date_type_code value

        Returns:
            gmd:CI_Date xml element
    """

    gco_date_element = create_xml_element(ns=NS_GCO, tag_name="Date", content=date)
    gmd_date_type_element = create_gmd_ci_datetypecode(date_type_code)
    content = gco_date_element + gmd_date_type_element
    return create_xml_element(ns=NS_GMD, tag_name="CI_Date", content=content)


def create_gmd_md_ifentifier(code: str):
    gmd_code_element = create_xml_element(ns=NS_GMD, tag_name="code", content=create_gco_character_string(code))
    return create_xml_element(ns=NS_GMD, tag_name="MD_Identifier", content=gmd_code_element)


def create_gmd_identifier(content: str):
    """
        mandatory subelements: MD_Identifier or RS_Identifier (content)
    """
    return create_xml_element(ns=NS_GMD, tag_name="identifier", content=content)


def create_gmd_citation(content: str):
    """
        mandatory subelements: CI_Citation (content)
    """
    return create_xml_element(ns=NS_GMD, tag_name="citation", content=content)


def create_gmd_ci_citation(gmd_title: str, gmd_date: str, gmd_identifier: str = ""):
    """
        mandatory subelements: title, date
        optional subelements: identifier
    """

    gmd_title = create_xml_element(ns=NS_GMD, tag_name="title", content=create_gco_character_string(gmd_title))
    content = gmd_title + gmd_date + gmd_identifier
    return create_xml_element(ns=NS_GMD, tag_name="CI_Citation", content=content)


def create_gmd_organisation_name(organization_name: str):
    return create_xml_element(ns=NS_GMD, tag_name="organisationName",
                              content=create_gco_character_string(organization_name))


def create_gmd_ci_responsible_party(gmd_role: str, organization_name: str = "", gmd_contact_info: str = ""):
    content = ""
    content += create_gmd_organisation_name(organization_name=organization_name)
    content += gmd_contact_info
    content += gmd_role

    return create_xml_element(ns=NS_GMD, tag_name="CI_ResponsibleParty", content=content)


def create_gmd_point_of_contact(gmd_role: str, organization_name: str = None, gmd_contact_info: str = None):
    gmd_ci_responsible_party = create_gmd_ci_responsible_party(gmd_role=gmd_role, organization_name=organization_name,
                                                               gmd_contact_info=gmd_contact_info)
    return create_xml_element(ns=NS_GMD, tag_name="pointOfContact", content=gmd_ci_responsible_party)


def create_gmd_ci_contact(gmd_phone: str = "", gmd_address: str = "", gmd_online_resource: str = "",
                          gmd_hours_of_service: str = "", gmd_contact_instructions: str = ""):
    content = ""
    content += gmd_phone
    content += gmd_address
    content += gmd_online_resource
    content += gmd_hours_of_service
    content += gmd_contact_instructions
    return create_xml_element(ns=NS_GMD, tag_name="CI_Contact", content=content)


def create_gmd_contact_info(gmd_phone: str = "", gmd_address: str = "", gmd_online_resource: str = "",
                            gmd_hours_of_service: str = "", gmd_contact_instructions: str = ""):
    gmd_ci_contact = create_gmd_ci_contact(gmd_phone=gmd_phone, gmd_address=gmd_address,
                                           gmd_online_resource=gmd_online_resource,
                                           gmd_hours_of_service=gmd_hours_of_service,
                                           gmd_contact_instructions=gmd_contact_instructions)
    return create_xml_element(ns=NS_GMD, tag_name="contactInfo", content=gmd_ci_contact)


def create_gmd_ci_role_code(role_code: str):
    """
        Mandatory Keywords:
            role_code:

        Returns:
            gmd:CI_RoleCode xml element
    """
    attributes = {
        "codeList": "http://standards.iso.org/ittf/PubliclyAvailableStandards/ISO_19139_Schemas/resources/codelist/ML_gmxCodelists.xml#CI_RoleCode",
        "codeListValue": role_code
    }
    return create_xml_element(ns=NS_GMD, tag_name="CI_RoleCode", content=role_code, attributes=attributes)


def create_gmd_role(role_code: str):
    """
        Mandatory Keywords:
            role_code:

        Returns:
            gmd:role xml element
    """
    return create_xml_element(ns=NS_GMD, tag_name="role", content=create_gmd_ci_role_code(role_code=role_code))


def create_gmd_abstract(abstract: str, ):
    return create_xml_element(ns=NS_GMD, tag_name="abstract", content=create_gco_character_string(abstract))


# Done
def create_gmd_md_maintenance_frequency_code(maintenance_frequency_code: str):
    """
        Mandatory Keywords:
            maintenance_frequency_code: gmd:MD_MaintenanceFrequencyCode
        Returns:
            gmd:MD_MaintenanceFrequencyCode xml element
    """
    md_maintenance_frequency_code_attributes = {
        "codeList": "http://www.isotc211.org/2005/resources/codeList.xml#MD_MaintenanceFrequencyCode",
        "codeListValue": maintenance_frequency_code
    }
    return create_xml_element(ns=NS_GMD, tag_name="MD_MaintenanceFrequencyCode",
                              attributes=md_maintenance_frequency_code_attributes)


# Done
def create_gmd_maintenance_and_update_frequency(maintenance_frequency_code: str):
    """
        Mandatory Keywords:
            maintenance_frequency_code: gmd:MD_MaintenanceFrequencyCode
        Returns:
            gmd:maintenanceAndUpdateFrequency xml element with gmd:MD_MaintenanceFrequencyCode as subelement
    """
    return create_xml_element(ns=NS_GMD, tag_name="maintenanceAndUpdateFrequency",
                              content=create_gmd_md_maintenance_frequency_code(
                                  maintenance_frequency_code=maintenance_frequency_code))


# Done
def create_gmd_md_maintenance_information(gmd_maintenance_and_update_frequency: str,
                                          gmd_date_of_next_update: str = "",
                                          gmd_user_defined_maintenance_frequency: str = "",
                                          gmd_update_scope: str = "",
                                          gmd_update_scope_description: str = "",
                                          gmd_maintenance_note: str = "",
                                          gmd_contact: str = ""):
    """
        Mandatory Keywords:
            gmd_md_maintenance_information: gmd:MD_MaintenanceFrequencyCode xml element
        Optional Keywords:
            gmd_date_of_next_update: choice of gco:Date or gco:DateTime
            gmd_user_defined_maintenance_frequency: gts:TM_PeriodDuration
            gmd_update_scope: gmd:MD_ScopeCode
            gmd_update_scope_description: gmd:MD_ScopeDescription
            gmd_maintenance_note: gmd:characterString
            gmd_contact: gmd:CI_ResponsibleParty
        Returns:
            gmd:MD_MaintenanceInformation xml element with all subelements elements
    """

    content = ""
    content += gmd_maintenance_and_update_frequency
    content += gmd_date_of_next_update  # ToDo: write function to generate the xml object
    content += gmd_user_defined_maintenance_frequency  # ToDo: write function to generate the xml object
    content += gmd_update_scope  # ToDo: write function to generate the xml object
    content += gmd_update_scope_description  # ToDo: write function to generate the xml object
    content += gmd_maintenance_note  # ToDo: write function to generate the xml object
    content += gmd_contact  # ToDo: write function to generate the xml object

    return create_xml_element(ns=NS_GMD, tag_name="MD_MaintenanceInformation", content=content)


# Done
def create_gmd_resource_maintenance(gmd_maintenance_and_update_frequency: str,
                                    gmd_date_of_next_update: str = "",
                                    gmd_user_defined_maintenance_frequency: str = "",
                                    gmd_update_scope: str = "",
                                    gmd_update_scope_description: str = "",
                                    gmd_maintenance_note: str = "",
                                    gmd_contact: str = ""):
    """
        Mandatory Keywords:
            gmd_md_maintenance_information: gmd:MD_MaintenanceFrequencyCode xml element
        Optional Keywords:
            gmd_date_of_next_update: choice of gco:Date or gco:DateTime
            gmd_user_defined_maintenance_frequency: gts:TM_PeriodDuration
            gmd_update_scope: gmd:MD_ScopeCode
            gmd_update_scope_description: gmd:MD_ScopeDescription
            gmd_maintenance_note: gmd:characterString
            gmd_contact: gmd:CI_ResponsibleParty
        Returns:
            gmd:resourceMaintenance xml element
    """
    return create_xml_element(ns=NS_GMD,
                              tag_name="resourceMaintenance",
                              content=create_gmd_md_maintenance_information(
                                  gmd_maintenance_and_update_frequency=gmd_maintenance_and_update_frequency,
                                  gmd_date_of_next_update=gmd_date_of_next_update,
                                  gmd_user_defined_maintenance_frequency=gmd_user_defined_maintenance_frequency,
                                  gmd_update_scope=gmd_update_scope,
                                  gmd_update_scope_description=gmd_update_scope_description,
                                  gmd_maintenance_note=gmd_maintenance_note,
                                  gmd_contact=gmd_contact))


def create_gmd_descriptive_keywords():
    """<gmd:descriptiveKeywords>
            <gmd:MD_Keywords>
                <gmd:keyword>
                    <gco:CharacterString>inspireidentifiziert</gco:CharacterString>
                </gmd:keyword>
            </gmd:MD_Keywords>
        </gmd:descriptiveKeywords>
    """


def create_gmd_resource_constraints():
    """
    <gmd:resourceConstraints>
        <gmd:MD_Constraints>
            <gmd:useLimitation>
                <gco:CharacterString>Wenn Sie Informationen bzgl. der Nutzungsbedingungen und anfallender Kosten brauchen, wenden Sie sich bitte an die angegebene Kontaktstelle.</gco:CharacterString>
            </gmd:useLimitation>
        </gmd:MD_Constraints>
    </gmd:resourceConstraints>
    <gmd:resourceConstraints>
        <gmd:MD_LegalConstraints>
            <gmd:accessConstraints>
                <gmd:MD_RestrictionCode codeList="http://standards.iso.org/ittf/PubliclyAvailableStandards/ISO_19139_Schemas/resources/codelist/ML_gmxCodelists.xml#MD_RetrictionCode" codeListValue="otherRestrictions">otherRestrictions</gmd:MD_RestrictionCode>
            </gmd:accessConstraints>
            <gmd:otherConstraints>
                <gco:CharacterString>Wenn Sie Informationen bzgl. vorhandener Zugriffsbeschränkungen brauchen, wenden Sie sich bitte an die angegebene Kontaktstelle.</gco:CharacterString>
            </gmd:otherConstraints>
        </gmd:MD_LegalConstraints>
    </gmd:resourceConstraints>
    """


def create_gmd_spatial_resolution():
    """
    <gmd:spatialResolution>
        <gmd:MD_Resolution>
            <gmd:equivalentScale>
                <gmd:MD_RepresentativeFraction>
                    <gmd:denominator>
                        <gco:Integer>625</gco:Integer>
                    </gmd:denominator>
                </gmd:MD_RepresentativeFraction>
            </gmd:equivalentScale>
        </gmd:MD_Resolution>
    </gmd:spatialResolution>
    """


def create_gmd_character_set():
    """<gmd:characterSet>
        <gmd:MD_CharacterSetCode codeList="http://www.isotc211.org/2005/resources/codeList.xml#MD_CharacterSetCode" codeListValue="utf8"/>
    </gmd:characterSet>"""


def create_gmd_topic_category():
    """
    <gmd:topicCategory>
        <gmd:MD_TopicCategoryCode>planningCadastre</gmd:MD_TopicCategoryCode>
    </gmd:topicCategory>
    """


def create_gmd_extent():
    """
    <gmd:extent>
        <gmd:EX_Extent>
            <gmd:geographicElement>
                <gmd:EX_BoundingPolygon>
                    <gmd:polygon>
                        <gml:MultiSurface gml:id="_6f987bd5951a7d8e5213541c3ccc62ee" srsName="EPSG:4326" xmlns:gml="http://www.opengis.net/gml">
                            <gml:surfaceMember>
                                <gml:Polygon gml:id="_a8d6d37005110c88ac36b92b26e71d0e">
                                    <gml:exterior>
                                        <gml:LinearRing>
                                            <gml:posList srsDimension="2">7.07968 50.533441 7.079991 50.533702 7.080095 50.533795 7.080181 50.533869 7.08044 50.534111 7.080697 50.534343 7.08089 50.534498 7.081144 50.534684 7.081532 50.534944 7.081684 50.535043 7.082207 50.535305 7.082305 50.535355 7.082356 50.535388 7.082698 50.535112 7.083019 50.534859 7.08322 50.534679 7.082713 50.534327 7.083098 50.534008 7.083293 50.533845 7.083473 50.533685 7.083889 50.533364 7.083994 50.533412 7.084262 50.533183 7.084627 50.532843 7.084729 50.532745 7.084833 50.532792 7.085117 50.532502 7.08525 50.532551 7.085304 50.532582 7.085385 50.532498 7.085735 50.532145 7.085915 50.531956 7.08598 50.53189 7.085657 50.531775 7.085391 50.531669 7.085279 50.531624 7.084952 50.531512 7.084257 50.531266 7.083747 50.531088 7.083274 50.53092 7.083104 50.53086 7.08258 50.530593 7.082499 50.530552 7.082147 50.53041 7.081288 50.5302 7.080651 50.530026 7.080121 50.529886 7.080102 50.529881 7.079681 50.53035 7.079398 50.530677 7.079167 50.530943 7.07891 50.531219 7.078955 50.531235 7.078857 50.531328 7.078671 50.531504 7.078345 50.531814 7.078413 50.531849 7.078369 50.531886 7.078301 50.531947 7.07821 50.532025 7.078316 50.532106 7.07859 50.532341 7.078968 50.532656 7.079151 50.532843 7.079491 50.53324 7.079618 50.533371 7.07968 50.533441</gml:posList>
                                        </gml:LinearRing>
                                    </gml:exterior>
                                </gml:Polygon>
                            </gml:surfaceMember>
                        </gml:MultiSurface>
                    </gmd:polygon>
                </gmd:EX_BoundingPolygon>
            </gmd:geographicElement>
        </gmd:EX_Extent>
    </gmd:extent>
    <gmd:extent>
        <gmd:EX_Extent>
            <gmd:geographicElement>
                <gmd:EX_GeographicBoundingBox>
                    <gmd:westBoundLongitude>
                        <gco:Decimal>7.07820994860938</gco:Decimal>
                    </gmd:westBoundLongitude>
                    <gmd:eastBoundLongitude>
                        <gco:Decimal>7.08597971353399</gco:Decimal>
                    </gmd:eastBoundLongitude>
                    <gmd:southBoundLatitude>
                        <gco:Decimal>50.529881283716</gco:Decimal>
                    </gmd:southBoundLatitude>
                    <gmd:northBoundLatitude>
                        <gco:Decimal>50.5353882475003</gco:Decimal>
                    </gmd:northBoundLatitude>
                </gmd:EX_GeographicBoundingBox>
            </gmd:geographicElement>
        </gmd:EX_Extent>
    </gmd:extent>
    <gmd:extent>
        <gmd:EX_Extent>
            <gmd:temporalElement>
                <gmd:EX_TemporalExtent>
                    <gmd:extent>
                        <gml:TimePeriod gml:id="temporalextent">
                            <gml:beginPosition>1957-12-19</gml:beginPosition>
                            <gml:endPosition>1961-01-07</gml:endPosition>
                        </gml:TimePeriod>
                    </gmd:extent>
                </gmd:EX_TemporalExtent>
            </gmd:temporalElement>
        </gmd:EX_Extent>
    </gmd:extent>
    """


def create_gmd_md_data_identification(gmd_citation: str,
                                      gmd_abstract: str,
                                      gmd_language: str,
                                      gmd_purpose: str = "",
                                      gmd_credit: [str] = [],
                                      gmd_status: [str] = [],
                                      gmd_point_of_contact: [str] = [],
                                      gmd_resource_maintenance: [str] = [],
                                      gmd_graphic_overview: [str] = [],
                                      gmd_resource_format: [str] = [],
                                      gmd_descriptive_keywords: [str] = [],
                                      gmd_resource_specific_usage: [str] = [],
                                      gmd_resource_constraints: [str] = [],
                                      gmd_aggregation_info: [str] = [],
                                      gmd_spatial_representation_type: [str] = [],
                                      gmd_spatial_resolution: [str] = [],
                                      gmd_character_set: [str] = [],
                                      gmd_topic_category: [str] = [],
                                      gmd_environment_description: str = "",
                                      gmd_extent: [str] = [],
                                      gmd_supplemental_information: str = ""):
    """
        Mandatory keywords:
            gmd_citation:
            gmd_abstract:
            gmd_language:
        Optional keywords:
            gmd_purpose:
            gmd_credit:
            gmd_status:
            gmd_point_of_contact:
            gmd_resource_maintenance:
            gmd_graphic_overview:
            gmd_resource_format:
            gmd_descriptive_keywords:
            gmd_resource_specific_usage:
            gmd_resource_constraints:
            gmd_aggregation_info:
            gmd_spatial_representation_type:
            gmd_spatial_resolution:
            gmd_character_set:
            gmd_topic_category:
            gmd_environment_description:
            gmd_extent:
            gmd_supplemental_information:
        Returns:
            gmd:MD_DataIdentification xml element with all mandatory subelements and optionals if they are provieded
    """
    content = f"""
                {gmd_citation}
                {gmd_abstract}
                {gmd_purpose}
                {" ".join(str(_gmd_credit) for _gmd_credit in gmd_credit)}
                {" ".join(str(_gmd_status) for _gmd_status in gmd_status)}
                {" ".join(str(_gmd_point_of_contact) for _gmd_point_of_contact in gmd_point_of_contact)}
                {" ".join(str(_gmd_resource_maintenance) for _gmd_resource_maintenance in gmd_resource_maintenance)}
                {" ".join(str(_gmd_graphic_overview) for _gmd_graphic_overview in gmd_graphic_overview)}
                {" ".join(str(_gmd_resource_format) for _gmd_resource_format in gmd_resource_format)}
                {" ".join(str(_gmd_descriptive_keywords) for _gmd_descriptive_keywords in gmd_descriptive_keywords)}
                {" ".join(str(_gmd_resource_specific_usage) for _gmd_resource_specific_usage in gmd_resource_specific_usage)}
                {" ".join(str(_gmd_resource_constraints) for _gmd_resource_constraints in gmd_resource_constraints)}
                {" ".join(str(_gmd_aggregation_info) for _gmd_aggregation_info in gmd_aggregation_info)}
                {" ".join(str(_gmd_spatial_representation_type) for _gmd_spatial_representation_type in gmd_spatial_representation_type)}
                {" ".join(str(_gmd_spatial_resolution) for _gmd_spatial_resolution in gmd_spatial_resolution)}
                {" ".join(str(_gmd_language) for _gmd_language in gmd_language)}
                {" ".join(str(_gmd_character_set) for _gmd_character_set in gmd_character_set)}
                {" ".join(str(_gmd_topic_category) for _gmd_topic_category in gmd_topic_category)}
                {gmd_environment_description}
                {" ".join(str(_gmd_extent) for _gmd_extent in gmd_extent)}
                {gmd_supplemental_information}
             """
    return create_xml_element(ns=NS_GMD, tag_name="MD_DataIdentification", content=content)


def create_gmd_identification_info(gmd_citation: str,
                                   gmd_abstract: str,
                                   gmd_language: str,
                                   gmd_purpose: str = "",
                                   gmd_credit: [str] = [],
                                   gmd_status: [str] = [],
                                   gmd_point_of_contact: [str] = [],
                                   gmd_resource_maintenance: [str] = [],
                                   gmd_graphic_overview: [str] = [],
                                   gmd_resource_format: [str] = [],
                                   gmd_descriptive_keywords: [str] = [],
                                   gmd_resource_specific_usage: [str] = [],
                                   gmd_resource_constraints: [str] = [],
                                   gmd_aggregation_info: [str] = [],
                                   gmd_spatial_representation_type: [str] = [],
                                   gmd_spatial_resolution: [str] = [],
                                   gmd_character_set: [str] = [],
                                   gmd_topic_category: [str] = [],
                                   gmd_environment_description: str = "",
                                   gmd_extent: [str] = [],
                                   gmd_supplemental_information: str = ""):
    gmd_md_data_identification = create_gmd_md_data_identification(gmd_citation=gmd_citation,
                                                                   gmd_abstract=gmd_abstract,
                                                                   gmd_language=gmd_language,
                                                                   gmd_purpose=gmd_purpose,
                                                                   gmd_credit=gmd_credit,
                                                                   gmd_status=gmd_status,
                                                                   gmd_point_of_contact=gmd_point_of_contact,
                                                                   gmd_resource_maintenance=gmd_resource_maintenance,
                                                                   gmd_graphic_overview=gmd_graphic_overview,
                                                                   gmd_resource_format=gmd_resource_format,
                                                                   gmd_descriptive_keywords=gmd_descriptive_keywords,
                                                                   gmd_resource_specific_usage=gmd_resource_specific_usage,
                                                                   gmd_resource_constraints=gmd_resource_constraints,
                                                                   gmd_aggregation_info=gmd_aggregation_info,
                                                                   gmd_spatial_representation_type=gmd_spatial_representation_type,
                                                                   gmd_spatial_resolution=gmd_spatial_resolution,
                                                                   gmd_character_set=gmd_character_set,
                                                                   gmd_topic_category=gmd_topic_category,
                                                                   gmd_environment_description=gmd_environment_description,
                                                                   gmd_extent=gmd_extent,
                                                                   gmd_supplemental_information=gmd_supplemental_information)

    return create_xml_element(ns=NS_GMD, tag_name="identificationInfo", content=gmd_md_data_identification)


def create_gmd_reference_system_info():
    # ToDo: RS_Identifier for all needed reference systems
    return f""" <gmd:referenceSystemInfo>
                    <gmd:MD_ReferenceSystem>
                        <gmd:referenceSystemIdentifier>
                            <gmd:RS_Identifier>
                                <gmd:authority>
                                    <gmd:CI_Citation>
                                        <gmd:title>
                                            <gco:CharacterString>European Petroleum Survey Group (EPSG) Geodetic Parameter Registry</gco:CharacterString>
                                        </gmd:title>
                                        <gmd:date>
                                            <gmd:CI_Date>
                                                <gmd:date>
                                                    <gco:Date>2008-11-12</gco:Date>
                                                </gmd:date>
                                                <gmd:dateType>
                                                    <gmd:CI_DateTypeCode codeList="http://www.isotc211.org/2005/resources/codelist/gmxCodelists.xml#CI_DateTypeCode" codeListValue="publication">publication</gmd:CI_DateTypeCode>
                                                </gmd:dateType>
                                            </gmd:CI_Date>
                                        </gmd:date>
                                        <gmd:citedResponsibleParty>
                                            <gmd:CI_ResponsibleParty>
                                                <gmd:organisationName>
                                                    <gco:CharacterString>European Petroleum Survey Group</gco:CharacterString>
                                                </gmd:organisationName>
                                                <gmd:contactInfo>
                                                    <gmd:CI_Contact>
                                                        <gmd:onlineResource>
                                                            <gmd:CI_OnlineResource>
                                                                <gmd:linkage>
                                                                    <gmd:URL>http://www.epsg-registry.org/</gmd:URL>
                                                                </gmd:linkage>
                                                            </gmd:CI_OnlineResource>
                                                        </gmd:onlineResource>
                                                    </gmd:CI_Contact>
                                                </gmd:contactInfo>
                                                <gmd:role gco:nilReason="missing"/>
                                            </gmd:CI_ResponsibleParty>
                                        </gmd:citedResponsibleParty>
                                    </gmd:CI_Citation>
                                </gmd:authority>
                                <gmd:code>
                                    <gco:CharacterString>http://www.opengis.net/def/crs/EPSG/0/31466</gco:CharacterString>
                                </gmd:code>
                                <gmd:version>
                                    <gco:CharacterString>6.18.3</gco:CharacterString>
                                </gmd:version>
                            </gmd:RS_Identifier>
                        </gmd:referenceSystemIdentifier>
                    </gmd:MD_ReferenceSystem>
                </gmd:referenceSystemInfo>
            """


def create_new_contact(organization_name: str, electronic_mail_address: str, ci_role: str):
    return f""" <gmd:contact>
                    <gmd:CI_ResponsibleParty>
                        <gmd:organisationName>
                            <gco:CharacterString>{organization_name}</gco:CharacterString>
                        </gmd:organisationName>
                        <gmd:contactInfo>
                            <gmd:CI_Contact>
                                <gmd:address>
                                    <gmd:CI_Address>
                                        <gmd:electronicMailAddress>
                                            <gco:CharacterString>{electronic_mail_address}</gco:CharacterString>
                                        </gmd:electronicMailAddress>
                                    </gmd:CI_Address>
                                </gmd:address>
                            </gmd:CI_Contact>
                        </gmd:contactInfo>
                        <gmd:role>-
                            <gmd:CI_RoleCode codeList="http://standards.iso.org/ittf/PubliclyAvailableStandards/ISO_19139_Schemas/resources/codelist/ML_gmxCodelists.xml#CI_RoleCode" codeListValue="{ci_role}">{ci_role}</gmd:CI_RoleCode>
                        </gmd:role>
                    </gmd:CI_ResponsibleParty>
                </gmd:contact>
        """


def create_new_md_metadata(date: str, gmd_file_identifier: str, gmd_contacts: str, gmd_reference_system_info: str,
                           gmd_identification_info: str):
    return f"""   <?xml version="1.0" encoding="utf-8"?>
                    <gmd:MD_Metadata xmlns:gco="http://www.isotc211.org/2005/gco" xmlns:gmd="http://www.isotc211.org/2005/gmd" xmlns:gml="http://www.opengis.net/gml" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.isotc211.org/2005/gmd http://schemas.opengis.net/iso/19139/20060504/gmd/gmd.xsd">
                        <gmd:fileIdentifier>
                            <gco:CharacterString>{gmd_file_identifier}</gco:CharacterString>
                        </gmd:fileIdentifier>
                        <gmd:characterSet>
                            <gmd:MD_CharacterSetCode codeList="http://standards.iso.org/ittf/PubliclyAvailableStandards/ISO_19139_Schemas/resources/codelist/ML_gmxCodelists.xml#MD_CharacterSetCode" codeListValue="utf8"/>
                        </gmd:characterSet>
                        <gmd:hierarchyLevel>
                            <gmd:MD_ScopeCode codeList="http://standards.iso.org/ittf/PubliclyAvailableStandards/ISO_19139_Schemas/resources/codelist/ML_gmxCodelists.xml#MD_ScopeCode" codeListValue="dataset">dataset</gmd:MD_ScopeCode>
                        </gmd:hierarchyLevel>
                        {gmd_contacts}
                        <gmd:dateStamp>
                            <gco:Date>{date}</gco:Date>
                        </gmd:dateStamp>
                        <gmd:metadataStandardName>
                            <gco:CharacterString>ISO19115</gco:CharacterString>
                        </gmd:metadataStandardName>
                        <gmd:metadataStandardVersion>
                            <gco:CharacterString>2003/Cor.1:2006</gco:CharacterString>
                        </gmd:metadataStandardVersion>
                        {gmd_reference_system_info}
                        {gmd_identification_info}
                        <gmd:distributionInfo>
                            <gmd:MD_Distribution>
                                <gmd:distributionFormat>
                                    <gmd:MD_Format>
                                        <gmd:name>
                                            <gco:CharacterString>GeoTIFF</gco:CharacterString>
                                        </gmd:name>
                                        <gmd:version>
                                            <gco:CharacterString>unkown</gco:CharacterString>
                                        </gmd:version>
                                    </gmd:MD_Format>
                                </gmd:distributionFormat>
                                <gmd:transferOptions>
                                    <gmd:MD_DigitalTransferOptions>
                                        <gmd:onLine>
                                            <gmd:CI_OnlineResource>
                                                <gmd:linkage>
                                                    <gmd:URL>https://komserv4gdi.service24.rlp.de/BPlan2/07131007_Bad_Neuenahr-Ahrweiler/pdf/BPlan.07131007.1001.0.plan.pdf</gmd:URL>
                                                </gmd:linkage>
                                                <gmd:function>
                                                    <gmd:CI_OnLineFunctionCode codeList="http://www.isotc211.org/2005/resources/Codelist/gmxCodelists.xml" codeListValue="download">download</gmd:CI_OnLineFunctionCode>
                                                </gmd:function>
                                            </gmd:CI_OnlineResource>
                                        </gmd:onLine>
                                    </gmd:MD_DigitalTransferOptions>
                                </gmd:transferOptions>
                            </gmd:MD_Distribution>
                        </gmd:distributionInfo>
                        <gmd:dataQualityInfo>
                            <gmd:DQ_DataQuality>
                                <gmd:scope>
                                    <gmd:DQ_Scope>
                                        <gmd:level>
                                            <gmd:MD_ScopeCode codeList="http://standards.iso.org/ittf/PubliclyAvailableStandards/ISO_19139_Schemas/resources/codelist/ML_gmxCodelists.xml#MD_ScopeCode" codeListValue="dataset">dataset</gmd:MD_ScopeCode>
                                        </gmd:level>
                                    </gmd:DQ_Scope>
                                </gmd:scope>
                                <gmd:report>
                                    <gmd:DQ_DomainConsistency xsi:type="gmd:DQ_DomainConsistency_Type">
                                        <gmd:result>
                                            <gmd:DQ_ConformanceResult xsi:type="gmd:DQ_ConformanceResult_Type">
                                                <gmd:specification>
                                                    <gmd:CI_Citation>
                                                        <gmd:title>
                                                            <gco:CharacterString>VERORDNUNG (EG) Nr. 1089/2010 DER KOMMISSION vom 23. November 2010 zur Durchführung der Richtlinie 2007/2/EG des Europäischen Parlaments und des Rates hinsichtlich der Interoperabilität von Geodatensätzen und -diensten</gco:CharacterString>
                                                        </gmd:title>
                                                        <gmd:date>
                                                            <gmd:CI_Date>
                                                                <gmd:date>
                                                                    <gco:Date>2010-12-08</gco:Date>
                                                                </gmd:date>
                                                                <gmd:dateType>
                                                                    <gmd:CI_DateTypeCode codeList="http://standards.iso.org/ittf/PubliclyAvailableStandards/ISO_19139_Schemas/resources/codelist/ML_gmxCodelists.xml#CI_DateTypeCode" codeListValue="publication">publication</gmd:CI_DateTypeCode>
                                                                </gmd:dateType>
                                                            </gmd:CI_Date>
                                                        </gmd:date>
                                                    </gmd:CI_Citation>
                                                </gmd:specification>
                                                <gmd:explanation>
                                                    <gco:CharacterString>No explanation available</gco:CharacterString>
                                                </gmd:explanation>
                                                <gmd:pass>
                                                    <gco:Boolean>false</gco:Boolean>
                                                </gmd:pass>
                                            </gmd:DQ_ConformanceResult>
                                        </gmd:result>
                                    </gmd:DQ_DomainConsistency>
                                </gmd:report>
                                <gmd:report>
                                    <gmd:DQ_DomainConsistency xsi:type="gmd:DQ_DomainConsistency_Type">
                                        <gmd:result>
                                            <gmd:DQ_ConformanceResult xsi:type="gmd:DQ_ConformanceResult_Type">
                                                <gmd:specification>
                                                    <gmd:CI_Citation>
                                                        <gmd:title>
                                                            <gco:CharacterString>Verordnung (EG) Nr. 1205/2008 der Kommission vom 3. Dezember 2008 zur Durchführung der Richtlinie 2007/2/EG des Europäischen Parlaments und des Rates hinsichtlich Metadaten</gco:CharacterString>
                                                        </gmd:title>
                                                        <gmd:date>
                                                            <gmd:CI_Date>
                                                                <gmd:date>
                                                                    <gco:Date>2008-12-03</gco:Date>
                                                                </gmd:date>
                                                                <gmd:dateType>
                                                                    <gmd:CI_DateTypeCode codeList="http://standards.iso.org/ittf/PubliclyAvailableStandards/ISO_19139_Schemas/resources/codelist/ML_gmxCodelists.xml#CI_DateTypeCode" codeListValue="publication">publication</gmd:CI_DateTypeCode>
                                                                </gmd:dateType>
                                                            </gmd:CI_Date>
                                                        </gmd:date>
                                                    </gmd:CI_Citation>
                                                </gmd:specification>
                                                <gmd:explanation>
                                                    <gco:CharacterString>No explanation available</gco:CharacterString>
                                                </gmd:explanation>
                                                <gmd:pass>
                                                    <gco:Boolean>true</gco:Boolean>
                                                </gmd:pass>
                                            </gmd:DQ_ConformanceResult>
                                        </gmd:result>
                                    </gmd:DQ_DomainConsistency>
                                </gmd:report>
                                <gmd:lineage>
                                    <gmd:LI_Lineage>
                                        <gmd:statement>
                                            <gco:CharacterString>Bebauungsplan wurde auf Basis der Liegenschaftskarte georeferenziert.</gco:CharacterString>
                                        </gmd:statement>
                                    </gmd:LI_Lineage>
                                </gmd:lineage>
                            </gmd:DQ_DataQuality>
                        </gmd:dataQualityInfo>
                    </gmd:MD_Metadata>
                    """


MD_KEYWORDS = """   <gmd:MD_Keywords>
                        <gmd:keyword>
                            <gco:CharacterString>
                            {}      
                            </gco:CharacterString>
                        </gmd:keyword>
                    </gmd:MD_Keywords>"""
