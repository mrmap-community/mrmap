"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 25.09.19

"""
import json
from copy import copy

from django.core.exceptions import ObjectDoesNotExist

from csw.utils.converter import DATE_STRF
from service.models import Dataset, Layer
from service.settings import INSPIRE_LEGISLATION_FILE, SERVICE_OPERATION_URI_TEMPLATE
from service.helper.enums import MetadataEnum, OGCServiceEnum
from service.helper import xml_helper
from lxml.etree import Element, _Element
from collections import OrderedDict, Iterable
from lxml import etree

from django.utils import timezone

from MrMap.settings import XML_NAMESPACES, GENERIC_NAMESPACE_TEMPLATE


class Iso19115MetadataBuilder:

    def __init__(self, md_id: int, metadata_type: MetadataEnum, use_legislation_amendment=False):
        from service.models import Metadata, FeatureType
        self.metadata = Metadata.objects.get(id=md_id)
        self.organization = self.metadata.contact

        if not self.metadata.is_dataset_metadata:
            self.service_version = self.metadata.get_service_version()
            self.service_type = self.metadata.get_service_type()

        if self.metadata.is_featuretype_metadata:
            self.service_type = OGCServiceEnum.WFS.value
            self.described_resource = FeatureType.objects.get(
                metadata=self.metadata
            ).parent_service
        elif self.metadata.is_dataset_metadata:
            self.described_resource = Dataset.objects.get(metadata=self.metadata)
            self.service_type = OGCServiceEnum.DATASET.value
        elif self.metadata.is_service_metadata:
            self.service_type = self.metadata.get_service_type()
            self.described_resource = self.metadata.service
        elif self.metadata.is_layer_metadata:
            self.service_type = OGCServiceEnum.WMS.value
            self.described_resource = Layer.objects.get(metadata=self.metadata)
        else:
            raise NotImplementedError
        
        self.reduced_nsmap = {
            "gml": XML_NAMESPACES.get("gml", ""),
            "srv": XML_NAMESPACES.get("srv", ""),
            "gmd": XML_NAMESPACES.get("gmd", ""),
            "gco": XML_NAMESPACES.get("gco", ""),
            "xlink": XML_NAMESPACES.get("xlink", ""),
            None : XML_NAMESPACES.get("xsi", ""),
            "schemaLocation": "http://schemas.opengis.net/csw/2.0.2/profiles/apiso/1.0.0/apiso.xsd",
        }

        # create prefix variables for faster usage
        self.gmd = "{" + self.reduced_nsmap.get("gmd") + "}"
        self.gco = "{" + self.reduced_nsmap.get("gco") + "}"
        self.srv = "{" + self.reduced_nsmap.get("srv") + "}"
        self.xsi = "{" + self.reduced_nsmap.get(None) + "}"

        # load inspire legislation
        with open(INSPIRE_LEGISLATION_FILE, "r", encoding="utf-8") as _file:
            self.regislations = json.load(_file)

        # create name LUT
        self.hierarchy_names = {
            "wms": {
                "en": "Web map service",
                "de": "Darstellungsdienst",
            },
            "wfs": {
                "en": "Web feature service",
                "de": "Downloaddienst",
            },
            "dataset": {
                "en": "Dataset",
                "de": "Datensatz",
            },
        }

        self.metadata_type = metadata_type.value
        self.use_legislation_amendment = use_legislation_amendment

    def generate_service_metadata(self):
        """ Creates a metadata document, following the ISO19115 standard

        As a guide to this generator, you may read the ISO19115 workbook:
        ftp://ftp.ncddc.noaa.gov/pub/Metadata/Online_ISO_Training/Intro_to_ISO/workbooks/MI_Metadata.pdf

        Returns:
            doc (str): The 'document' content
        """
        root = Element(
            "{}MD_Metadata".format(self.gmd),
            nsmap=self.reduced_nsmap,
            attrib={
                "{}schemaLocation".format(self.xsi): self.reduced_nsmap.get("schemaLocation")
            }
        )

        subs = [
            self._create_file_identifier,
            self._create_language,
            self._create_character_set,
            self._create_hierarchy_level,
            self._create_hierarchy_level_name,
            self._create_contact,
            self._create_date_stamp,
            self._create_metadata_standard_name,
            self._create_metadata_standard_version,
            self._create_reference_system_info,
            self._create_identification_info,
            self._create_distribution_info,
            self._create_data_quality_info,
        ]

        for func in subs:
            sub_element = func()
            if not isinstance(sub_element, _Element) and isinstance(sub_element, Iterable):
                for elem in sub_element:
                    xml_helper.add_subelement(root, elem)
            else:
                xml_helper.add_subelement(root, sub_element)

        doc = etree.tostring(root, xml_declaration=True, encoding="utf-8", pretty_print=True)

        return doc

    def _create_file_identifier(self):
        """ Creates the <gmd:fileIdentifier> element

        Returns:
             ret_elem (_Element): The requested xml element
        """
        ret_elem = Element(
            self.gmd + "fileIdentifier"
        )
        elem = Element(
            self.gco + "CharacterString"
        )
        elem.text = self.metadata.uuid
        xml_helper.add_subelement(ret_elem, elem)
        return ret_elem

    def _create_language(self):
        """ Creates the <gmd:language> element

        Returns:
             ret_elem (_Element): The requested xml element
        """
        ret_elem = Element(
            self.gmd + "language"
        )
        lang = "ger"  # ToDo: Create here something dynamic so we can provide international self.metadata as well
        code_list = "http://standards.iso.org/ittf/PubliclyAvailableStandards/ISO_19139_Schemas/resources/codelist/ML_gmxCodelists.xml#LanguageCode"
        elem = Element(
            self.gmd + "LanguageCode",
            attrib={
                "codeList": code_list,
                "codeListValue": lang,
            }
        )
        elem.text = lang
        xml_helper.add_subelement(ret_elem, elem)
        return ret_elem

    def _create_character_set(self):
        """ Creates the <gmd:characterSet> element

        Returns:
             ret_elem (_Element): The requested xml element
        """
        ret_elem = Element(
            self.gmd + "characterSet"
        )
        char_set = "utf8"
        char_set_list = "http://standards.iso.org/ittf/PubliclyAvailableStandards/ISO_19139_Schemas/resources/codelist/ML_gmxCodelists.xml#MD_CharacterSetCode"
        elem = Element(
            self.gmd + "MD_CharacterSetCode",
            attrib={
                "codeList": char_set_list,
                "codeListValue": char_set,
            }
        )
        elem.text = char_set
        xml_helper.add_subelement(ret_elem, elem)
        return ret_elem

    def _create_hierarchy_level(self):
        """ Creates the <gmd:hierarchyLevel> element

        Returns:
             ret_elem (_Element): The requested xml element
        """
        hierarchy_level = self.metadata.metadata_type.type
        hierarchy_level_list = "http://standards.iso.org/ittf/PubliclyAvailableStandards/ISO_19139_Schemas/resources/codelist/ML_gmxCodelists.xml#MD_ScopeCode"
        ret_elem = Element(
            self.gmd + "hierarchyLevel"
        )
        elem = Element(
            self.gmd + "MD_ScopeCode",
            attrib={
                "codeList": hierarchy_level_list,
                "codeListValue": hierarchy_level,
            }
        )
        elem.text = hierarchy_level
        xml_helper.add_subelement(ret_elem, elem)
        return ret_elem

    def _create_hierarchy_level_name(self):
        """ Creates the <gmd:hierarchyLevelName> element

        Returns:
             ret_elem (_Element): The requested xml element
        """
        name = self.hierarchy_names[self.service_type]["de"]  # ToDo: Find international solution for this

        ret_elem = Element(
            self.gmd + "hierarchyLevelName"
        )
        elem = Element(
            self.gco + "CharacterString"
        )
        elem.text = name
        xml_helper.add_subelement(ret_elem, elem)
        return ret_elem

    def _create_contact(self):
        """ Creates the <gmd:CI_ResponsibleParty> element

        Returns:
             resp_party_elem (_Element): The responsible party xml element
        """
        ret_elem = Element(
            self.gmd + "contact"
        )

        resp_party_elem = Element(
            self.gmd + "CI_ResponsibleParty"
        )

        # gmd:individualName
        if self.organization.person_name is not None:
            indiv_name_elem = Element(
                self.gmd + "individualName"
            )
            char_str_elem = Element(
                self.gco + "CharacterString"
            )
            char_str_elem.text = self.organization.person_name
            xml_helper.add_subelement(indiv_name_elem, char_str_elem)
            xml_helper.add_subelement(resp_party_elem, indiv_name_elem)

        # gmd:organisationName
        if self.organization.organization_name is not None:
            org_name_elem = Element(
                self.gmd + "organisationName"
            )
            char_str_elem = Element(
                self.gco + "CharacterString"
            )
            char_str_elem.text = self.organization.organization_name
            xml_helper.add_subelement(org_name_elem, char_str_elem)
            xml_helper.add_subelement(resp_party_elem, org_name_elem)

        # gmd:positionName
        # ToDo: We do not persist the position of a person. Maybe this is required in the future, maybe never.
        # As long as we do not really use this, we fill this element as suggested in the iso19115 workbook, p. 45
        pos_name_elem = Element(
            self.gmd + "positionName",
            attrib={
                self.gco + "nilReason": "unknown",
            }
        )
        resp_party_elem.append(pos_name_elem)

        # gmd:contactInfo
        contact_info_elem = Element(
            self.gmd + "contactInfo"
        )
        contact_info_content_elem = self._create_contact_info_element()
        contact_info_elem.append(contact_info_content_elem)
        resp_party_elem.append(contact_info_elem)

        # gmd:role
        role_elem = Element(
            self.gmd + "role"
        )
        role_content_elem = self._create_role_element()
        role_elem.append(role_content_elem)
        resp_party_elem.append(role_elem)

        xml_helper.add_subelement(ret_elem, resp_party_elem)

        return ret_elem

    def _create_contact_info_element(self):
        """ Creates the <gmd:CI_Contact> element with it's subelements
        
        Returns:
             contact_elem (_Element): The contact information xml element
        """
        contact_elem = Element(
            self.gmd + "CI_Contact"
        )

        # gmd:phone
        phone_elem = Element(
            self.gmd + "phone"
        )
        ci_phone_elem = Element(
            self.gmd + "CI_Telephone"
        )
        if self.organization.phone is not None:
            voice_elem = Element(
                self.gmd + "voice"
            )
            voice_char_str_elem = Element(
                self.gco + "CharacterString"
            )
            voice_char_str_elem.text = self.organization.phone

            voice_elem.append(voice_char_str_elem)
            ci_phone_elem.append(voice_elem)

        if self.organization.facsimile is not None:
            facsimile_elem = Element(
                self.gmd + "facsimile"
            )
            facs_char_str_elem = Element(
                self.gco + "CharacterString"
            )
            facs_char_str_elem.text = self.organization.facsimile

            facsimile_elem.append(facs_char_str_elem)
            ci_phone_elem.append(facsimile_elem)

        phone_elem.append(ci_phone_elem)
        contact_elem.append(phone_elem)

        address_ret_dict = self._create_address_element()
        address_elem = address_ret_dict["element"]
        num_address_subelements = address_ret_dict["num_subelements"]

        # only add the address element if we have at least one subelement inside
        if num_address_subelements > 0:
            contact_elem.append(address_elem)

        online_resource_elem = self._create_online_resource()
        contact_elem.append(online_resource_elem)

        return contact_elem

    def _create_address_element(self):
        """ Creates the <gmd:address> element with it's subelements
        
        Returns:
             dict: Contains 'element' and 'num_subelements'
        """
        # gmd:address
        address_elem = Element(
            self.gmd + "address"
        )
        ci_address_elem = Element(
            self.gmd + "CI_Address"
        )
        address_elem.append(ci_address_elem)
        address_elements = 0

        # gmd:address/../self.gmd:deliveryPoint
        if self.organization.address is not None:
            address_elements += 1
            tmp_elem = Element(
                self.gmd + "deliveryPoint"
            )
            char_str_elem = Element(
                self.gco + "CharacterString"
            )
            char_str_elem.text = self.organization.address
            tmp_elem.append(char_str_elem)
            ci_address_elem.append(tmp_elem)

        # gmd:address/../self.gmd:city
        if self.organization.city is not None:
            address_elements += 1
            tmp_elem = Element(
                self.gmd + "city"
            )
            char_str_elem = Element(
                self.gco + "CharacterString"
            )
            char_str_elem.text = self.organization.city
            tmp_elem.append(char_str_elem)
            ci_address_elem.append(tmp_elem)

        # gmd:address/../self.gmd:administrativeArea
        # ToDo: We are not doing this, since this information is not provided by the usual self.metadata

        # gmd:address/../self.gmd:postalCode
        if self.organization.postal_code is not None:
            address_elements += 1
            tmp_elem = Element(
                self.gmd + "postalCode"
            )
            char_str_elem = Element(
                self.gco + "CharacterString"
            )
            char_str_elem.text = self.organization.postal_code
            tmp_elem.append(char_str_elem)
            ci_address_elem.append(tmp_elem)

        # gmd:address/../self.gmd:country
        if self.organization.country is not None:
            address_elements += 1
            tmp_elem = Element(
                self.gmd + "country"
            )
            char_str_elem = Element(
                self.gco + "CharacterString"
            )
            char_str_elem.text = self.organization.country
            tmp_elem.append(char_str_elem)
            ci_address_elem.append(tmp_elem)

        # gmd:address/../self.gmd:electronicMailAddress
        if self.organization.email is not None:
            address_elements += 1
            tmp_elem = Element(
                self.gmd + "electronicMailAddress"
            )
            char_str_elem = Element(
                self.gco + "CharacterString"
            )
            char_str_elem.text = self.organization.email
            tmp_elem.append(char_str_elem)
            ci_address_elem.append(tmp_elem)


        return {
            "element": address_elem,
            "num_subelements": address_elements,
        }

    def _create_online_resource(self):
        """ Creates the <gmd:CI_OnlineResource> element with it's subelements
        
        Returns:
             contact_elem (_Element): The contact information xml element
        """
        resource_elem = Element(
            self.gmd + "onlineResource"
        )
        ci_resource_elem = Element(
            self.gmd + "CI_OnlineResource"
        )

        resource_elem.append(ci_resource_elem)

        # gmd:linkage
        linkage_elem = Element(
            self.gmd + "linkage"
        )
        tmp_elem = Element(
            self.gmd + "URL"
        )
        if self.metadata.use_proxy_uri:
            tmp_elem.text = SERVICE_OPERATION_URI_TEMPLATE.format(self.metadata.id)
        else:
            tmp_elem.text = self.metadata.capabilities_original_uri
        ci_resource_elem.append(linkage_elem)
        linkage_elem.append(tmp_elem)

        # gmd:protocol
        protocol_elem = Element(
            self.gmd + "protocol"
        )
        tmp_elem = Element(
            self.gmd + "CharacterString"
        )
        tmp_elem.text = "HTTP"
        ci_resource_elem.append(protocol_elem)
        protocol_elem.append(tmp_elem)

        # gmd:applicationProfile
        app_profile_elem = Element(
            self.gmd + "applicationProfile",
            attrib={
                self.gco + "nilReason": "unknown",
            }
        )
        ci_resource_elem.append(app_profile_elem)

        # gmd:name
        name_elem = Element(
            self.gmd + "name"
        )
        tmp_elem = Element(
            self.gmd + "CharacterString"
        )
        tmp_elem.text = self.metadata.title
        ci_resource_elem.append(name_elem)
        name_elem.append(tmp_elem)

        # gmd:description
        descr_elem = Element(
            self.gmd + "description",
            attrib={
                self.gco + "nilReason": "unknown",
            }
        )
        ci_resource_elem.append(descr_elem)

        # gmd:function
        func_elem = Element(
            self.gmd + "function",
            attrib={
                self.gco + "nilReason": "unknown",
            }
        )
        ci_resource_elem.append(func_elem)

        return resource_elem

    def _create_role_element(self):
        """ Creates the <gmd:role> element
        
        Returns:
             ci_role_elem (_Element): The role information xml element
        """
        val_list = "https://standards.iso.org/ittf/PubliclyAvailableStandards/ISO_19139_Schemas/resources/codelist/ML_gmxCodelists.xml#CI_RoleCode"
        val = "pointOfContact"

        ci_role_elem = Element(
            self.gmd + "CI_RoleCode",
            attrib={
                "codeList": val_list,
                "codeListValue": val,
                "codeSpace": "007"
            }
        )
        ci_role_elem.text = val
        return ci_role_elem

    def _create_date_stamp(self):
        """ Creates the <gmd:dateStamp> element

        Returns:
             ret_elem (_Element): The requested xml element
        """
        ret_elem = Element(
            self.gmd + "dateStamp"
        )

        elem = Element(self.gco + "Date")

        if self.metadata.last_remote_change is not None:
            date = self.metadata.last_remote_change

        elif self.metadata.created is not None:
            date = self.metadata.created

        elif self.metadata.last_modified is not None:
            date = self.metadata.last_modified
        else:
            date = timezone.now()

        date = date.date().__str__()
        elem.text = date

        xml_helper.add_subelement(ret_elem, elem)

        return ret_elem

    def _create_metadata_standard_name(self):
        """ Creates the <gmd:self.metadataStandardName> element

        Returns:
             ret_elem (_Element): The requested xml element
        """
        ret_elem = Element(
            self.gmd + "metadataStandardName"
        )
        elem = Element(
            self.gco + "CharacterString"
        )
        elem.text = "ISO 19115 Geographic information - Metadata"

        xml_helper.add_subelement(ret_elem, elem)

        return ret_elem

    def _create_metadata_standard_version(self):
        """ Creates the <gmd:self.metadataStandardVersion> element

        Returns:
             ret_elem (_Element): The requested xml element
        """
        ret_elem = Element(
            self.gmd + "metadataStandardVersion"
        )
        elem = Element(
            self.gco + "CharacterString"
        )
        elem.text = "ISO 19115:2003(E)"

        xml_helper.add_subelement(ret_elem, elem)

        return ret_elem

    def _create_reference_system_info(self):
        """ Creates the <gmd:referenceSystemInfo> element

        Returns:
             ret_elem (_Element): The requested xml element
        """
        ref_systems = self.metadata.reference_system.all()
        ret_list = []

        for ref_sys in ref_systems:
            ret_elem = Element(
                self.gmd + "referenceSystemInfo"
            )
            md_ref_sys_ident_elem = Element(
                self.gmd + "MD_ReferenceSystem"
            )
            ref_sys_ident_elem = Element(
                self.gmd + "referenceSystemIdentifier"
            )
            rs_ident_elem = Element(
                self.gmd + "RS_Identifier"
            )
            code_elem = Element(
                self.gmd + "code"
            )
            char_elem = Element(
                self.gco + "CharacterString"
            )
            char_elem.text = "{}{}".format(ref_sys.prefix, ref_sys.code)

            xml_helper.add_subelement(ret_elem, md_ref_sys_ident_elem)
            xml_helper.add_subelement(md_ref_sys_ident_elem, ref_sys_ident_elem)
            xml_helper.add_subelement(ref_sys_ident_elem, rs_ident_elem)
            xml_helper.add_subelement(rs_ident_elem, code_elem)
            xml_helper.add_subelement(code_elem, char_elem)

            ret_list.append(ret_elem)

        return ret_list

    def _create_identification_info(self):
        """ Creates the <gmd:identificationInfo> element

        Returns:
             ret_elem (_Element): The requested xml element
        """
        ret_elem = Element(
            self.gmd + "identificationInfo"
        )

        # First create basic identification infos, which can be found in service, as well as dataset metadata
        id_info_elem = self._create_base_identification_info()

        # Then add specific identification info to the base info
        if self.service_type == OGCServiceEnum.DATASET.value:
            self._create_data_identification_info(id_info_elem)
        else:
            self._create_sv_identification_info(id_info_elem)

        xml_helper.add_subelement(ret_elem, id_info_elem)

        return ret_elem

    def _create_base_identification_info(self):
        """ Creates the <gmd:identificationInfo> element

        Only creates the elements, which are present in service as well as in dataset metadata

        Returns:
             ret_elem (_Element): The requested xml element
        """
        if self.service_type == OGCServiceEnum.DATASET.value:
            ret_elem = Element(
                self.gmd + "MD_DataIdentification"
            )
        else:
            ret_elem = Element(
                self.srv + "SV_ServiceIdentification"
            )

        # gmd:citation
        citation_elem = self._create_citation()
        ret_elem.append(citation_elem)

        # gmd:abstract
        abstract_elem = Element(
            self.gmd + "abstract"
        )
        char_str_elem = Element(
            self.gco + "CharacterString"
        )
        char_str_elem.text = self.metadata.abstract
        abstract_elem.append(char_str_elem)
        ret_elem.append(abstract_elem)

        # gmd:purpose
        # NOTE: We do not use this so far, but keep this in the code as a preparation for one day
        # purpose_elem = Element(
        #     self.gmd + "purpose"
        # )

        # gmd:credit
        # NOTE: We do not use this so far, but keep this in the code as a preparation for one day
        # credit_elem = Element(
        #     self.gmd + "credit"
        # )

        # gmd:status
        # NOTE: We do not use this so far, but keep this in the code as a preparation for one day
        # status_elem = Element(
        #     self.gmd + "status"
        # )

        # gmd:pointOfContact
        point_of_contact_elem = Element(
            self.gmd + "pointOfContact"
        )
        # _create_contact() returns the wrapping <gmd:contact> element, which is not needed here. We simply take the inner element and continue
        point_of_contact_content_elem = self._create_contact()
        point_of_contact_content_elem = xml_helper.try_get_single_element_from_xml("./" + GENERIC_NAMESPACE_TEMPLATE.format("CI_ResponsibleParty"), point_of_contact_content_elem)
        point_of_contact_elem.append(point_of_contact_content_elem)
        ret_elem.append(point_of_contact_elem)

        # gmd:resourceMaintenance
        # NOTE: We do not use this so far, but keep this in the code as a preparation for one day
        # resource_maintenance_elem = Element(
        #     self.gmd + "resourceMaintenance"
        # )

        # gmd:graphicOverview
        # NOTE: We do not use this so far, but keep this in the code as a preparation for one day
        # graphic_overview_elem = Element(
        #     self.gmd + "graphicOverview"
        # )

        # gmd:resourceFormat
        # NOTE: We do not use this so far, but keep this in the code as a preparation for one day
        # resource_format_elem = Element(
        #     self.gmd + "resourceFormat"
        # )

        # gmd:descriptiveKeywords
        descr_keywords_elem = self._create_keywords()
        ret_elem.append(descr_keywords_elem)

        # gmd:resourceSpecificUsage
        # NOTE: We do not use this so far, but keep this in the code as a preparation for one day
        # res_specific_usage_elem = Element(
        #     self.gmd + "resourceSpecificUsage"
        # )

        # gmd:resourceConstraints
        res_constraints_elem = Element(
            self.gmd + "resourceConstraints"
        )
        res_constraints_content_elem = self._create_legal_constraints()
        res_constraints_elem.append(res_constraints_content_elem)
        ret_elem.append(res_constraints_elem)

        # gmd:aggregationInfo
        # NOTE: We do not use this so far, but keep this in the code as a preparation for one day
        # aggregation_info_elem = Element(
        #     self.gmd + "aggregationInfo"
        # )

        return ret_elem

    def _create_sv_identification_info(self, upper_elem: Element):
        """ Creates the <srv:SV_ServiceIdentification> element contents

        Adds it's elements to a given base information element (upper_elem)

        Args:
            upper_elem (Element): The base info element
        Returns:
             ret_elem (_Element): The requested xml element
        """
        # srv:serviceType
        service_type_elem = Element(
            self.srv + "serviceType",
        )
        locale_name_elem = Element(
            self.gco + "LocalName"
        )
        # resolve service type according to best practice
        if self.service_type == 'wms':
            service_type = "WebMapService"
        elif self.service_type == 'wfs':
            service_type = "WebFeatureService"
        else:
            service_type = "unknown"
        service_type_version = self.service_version
        locale_name_elem.text = "urn:ogc:serviceType:{}:{}".format(service_type, service_type_version)
        service_type_elem.append(locale_name_elem)
        upper_elem.append(service_type_elem)

        # srv:serviceTypeVersion
        service_version_elem = Element(
            self.srv + "serviceTypeVersion",
        )
        char_str_elem = Element(
            self.gco + "CharacterString"
        )
        char_str_elem.text = service_type_version.value
        service_version_elem.append(char_str_elem)
        upper_elem.append(service_version_elem)

        # srv:accessProperties
        # NOTE: We do not use this so far, but keep this in the code as a preparation for one day
        # access_properties_elem = Element(
        #     self.srv + "accessProperties"
        # )

        # srv:restrictions
        # NOTE: We do not use this so far, but keep this in the code as a preparation for one day
        # restrictions_elem = Element(
        #     self.srv + "restrictions"
        # )

        # srv:keywords
        # NOTE: We do not use this so far, but keep this in the code as a preparation for one day
        # keywords_elem = Element(
        #     self.srv + "keywords"
        # )

        # srv:extent
        extent_elem = Element(
            self.srv + "extent"
        )
        extent_content_elem = self._create_extent_geographic()
        extent_elem.append(extent_content_elem)
        upper_elem.append(extent_elem)

        # srv:couplingType
        coupling_type_elem = Element(
            self.srv + "couplingType",
        )
        coupling_type_content_elem = Element(
            self.srv + "SV_CouplingType",
            attrib={
                "codeList": "SV_CouplingType",
                "codeListValue": "tight"
            }
        )
        coupling_type_elem.append(coupling_type_content_elem)
        upper_elem.append(coupling_type_elem)

        # srv:coupledResource
        # NOTE: We do not use this so far, but keep this in the code as a preparation for one day
        # coupled_res_elem = Element(
        #     self.srv + "coupledResource"
        # )

        # srv:containsOperations
        contains_op_elem = Element(
            self.srv + "containsOperations"
        )
        contains_op_content_elem = self._create_operation_metadata()
        contains_op_elem.append(contains_op_content_elem)
        upper_elem.append(contains_op_elem)

        # srv:operatesOn
        # NOTE: We do not use this so far, but keep this in the code as a preparation for one day
        # operates_on_elem = Element(
        #     self.srv + "operatesOn"
        # )

        return upper_elem

    def _create_data_identification_info(self, upper_elem: Element):
        """ Creates the <gmd:MD_DataIdentification> element contents

        Adds it's elements to a given base information element (upper_elem)

        Args:
            upper_elem (Element): The base info element
        Returns:
             ret_elem (_Element): The requested xml element
        """
        elems = [
            self._create_character_set,
            self._create_language,
            self._create_topic_category,
            self._create_extent_geographic,
        ]
        
        for func in elems:
            elem = func()
            if not isinstance(elem, _Element) and isinstance(elem, Iterable):
                for e in elem:
                    upper_elem.append(e)
            else:
                upper_elem.append(elem)

    def _create_topic_category(self):
        """ Creates the <gmd:topicCategory> element

        Returns:
             ret_list (list): A list of requested xml elements
        """
        ret_list = []
        for category in self.metadata.categories.all():
            topic_elem = Element(
                self.gmd + "topicCategory"
            )
            code_elem = Element(
                self.gmd + "MD_TopicCategoryCode"
            )
            topic_elem.append(code_elem)
            code_elem.text = category.title_EN
            ret_list.append(topic_elem)
        return ret_list

    def _create_citation(self):
        """ Creates the <gmd:citation> element

        Returns:
             ret_elem (_Element): The requested xml element
        """
        ret_elem = Element(
            self.gmd + "citation"
        )
        ci_citation_elem = Element(
            self.gmd + "CI_Citation"
        )
        ret_elem.append(ci_citation_elem)

        # gmd:title
        title_elem = Element(
            self.gmd + "title"
        )
        title_elem.text = self.metadata.title
        ci_citation_elem.append(title_elem)

        # gmd:alternateTitle
        alt_title_elem = Element(
            self.gmd + "alternateTitle",
            attrib={
                self.gco + "nilReason": "unknown",
            }
        )
        ci_citation_elem.append(alt_title_elem)

        # gmd:date
        date_elem = self._create_date_stamp()
        ci_citation_elem.append(date_elem)

        # gmd:edition
        edition_elem = Element(
            self.gmd + "edition",
            attrib={
                self.gco + "nilReason": "unknown",
            }
        )
        ci_citation_elem.append(edition_elem)

        # gmd:editionDate
        edition_date_elem = Element(
            self.gmd + "editionDate",
            attrib={
                self.gco + "nilReason": "unknown",
            }
        )
        ci_citation_elem.append(edition_date_elem)

        # gmd:identifier
        identifier_elem = Element(
            self.gmd + "identifier"
        )
        identifier_elem.text = self.metadata.identifier
        ci_citation_elem.append(identifier_elem)

        # gmd:citedResponsibleParty
        cited_resp_party_elem = Element(
            self.gmd + "citedResponsibleParty"
        )
        cited_resp_party_content_elem = self._create_contact()
        cited_resp_party_elem.append(cited_resp_party_content_elem)
        ci_citation_elem.append(cited_resp_party_elem)

        # gmd:presentationForm
        presentation_form_elem = Element(
            self.gmd + "presentationForm",
            attrib={
                self.gco + "nilReason": "unknown",
            }
        )
        ci_citation_elem.append(presentation_form_elem)

        # gmd:series
        series_elem = Element(
            self.gmd + "series",
            attrib={
                self.gco + "nilReason": "unknown",
            }
        )
        ci_citation_elem.append(series_elem)

        # gmd:otherCitationDetails
        cit_details_elem = Element(
            self.gmd + "otherCitationDetails",
            attrib={
                self.gco + "nilReason": "unknown",
            }
        )
        ci_citation_elem.append(cit_details_elem)

        # gmd:collectiveTitle
        collective_title_elem = Element(
            self.gmd + "collectiveTitle",
            attrib={
                self.gco + "nilReason": "unknown",
            }
        )
        ci_citation_elem.append(collective_title_elem)

        # gmd:ISBN
        isbn_elem = Element(
            self.gmd + "ISBN",
            attrib={
                self.gco + "nilReason": "unknown",
            }
        )
        ci_citation_elem.append(isbn_elem)

        # gmd:ISSN
        issn_elem = Element(
            self.gmd + "ISSN",
            attrib={
                self.gco + "nilReason": "unknown",
            }
        )
        ci_citation_elem.append(issn_elem)

        return ret_elem

    def _create_keywords(self):
        """ Creates the <gmd:MD_Keywords> element

        Returns:
             ret_elem (_Element): The requested xml element
        """
        descr_keywords_elem = Element(
            self.gmd + "descriptiveKeywords"
        )
        md_keywords_elem = Element(
            self.gmd + "MD_Keywords"
        )
        descr_keywords_elem.append(md_keywords_elem)

        keywords = self.metadata.keywords.all()
        for keyword in keywords:
            keyword_elem = Element(
                self.gmd + "keyword"
            )
            char_str_elem = Element(
                self.gco + "CharacterString"
            )
            char_str_elem.text = keyword.keyword

            keyword_elem.append(char_str_elem)
            md_keywords_elem.append(keyword_elem)

        return descr_keywords_elem

    def _create_legal_constraints(self):
        """ Creates the <gmd:MD_LegalConstraints> element

        Returns:
             ret_elem (_Element): The requested xml element
        """
        ret_elem = Element(
            self.gmd + "MD_LegalConstraints"
        )

        # gmd:useLimitation
        use_limitation_elem = Element(
            self.gmd + "useLimitation",
            attrib={
                self.gco + "nilReason": "unknown"
            }
        )
        ret_elem.append(use_limitation_elem)

        # gmd:accessConstraints
        access_constraints_elem = Element(
            self.gmd + "accessConstraints",
        )
        code_list = "http://standards.iso.org/ittf/PubliclyAvailableStandards/ISO_19139_Schemas/resources/codelist/ML_gmxCodelists.xml#MD_RestrictionCode"
        code_list_val = "otherRestrictions"
        md_restr_code_elem = Element(
            self.gmd + "MD_RestrictionCode",
            attrib={
                "codeList": code_list,
                "codeListValue": code_list_val,
            }
        )
        md_restr_code_elem.text = code_list_val
        access_constraints_elem.append(md_restr_code_elem)
        ret_elem.append(access_constraints_elem)

        # gmd:otherConstraints
        other_constraints_elem = Element(
            self.gmd + "otherConstraints",
        )
        char_str_elem = Element(
            self.gco + "CharacterString"
        )
        constraints_text = "no constraints"
        if self.metadata.access_constraints is not None and len(self.metadata.access_constraints) > 0:
            constraints_text = self.metadata.access_constraints
        char_str_elem.text = constraints_text
        other_constraints_elem.append(char_str_elem)
        ret_elem.append(other_constraints_elem)

        return ret_elem

    def _create_extent_geographic(self):
        """ Creates the <gmd:EX_Extent> element

        Returns:
             ret_elem (_Element): The requested xml element
        """
        ret_elem = Element(
            self.gmd + "EX_Extent"
        )

        # gmd:description
        descr_elem = Element(
            self.gmd + "description",
            attrib={
                self.gco + "nilReason": "unknown"
            }
        )
        ret_elem.append(descr_elem)

        # gmd:geographicElement
        geographic_elem = Element(
            self.gmd + "geographicElement"
        )
        try:
            geographic_content_elem = self._create_bounding_box()
            geographic_elem.append(geographic_content_elem)
        except ObjectDoesNotExist:
            # there was no bounding box in the whole service
            geographic_elem = Element(
                self.gmd + "geographicElement",
                attrib={
                    self.gco + "nilReason": "unknown"
                }
            )
        ret_elem.append(geographic_elem)

        # gmd:temporalElement
        temp_elem = Element(
            self.gmd + "temporalElement",
            attrib={
                self.gco + "nilReason": "unknown"
            }
        )
        ret_elem.append(temp_elem)

        # gmd:verticalElement
        vertical_elem = Element(
            self.gmd + "verticalElement",
            attrib={
                self.gco + "nilReason": "unknown"
            }
        )
        ret_elem.append(vertical_elem)

        return ret_elem

    def _create_bounding_box(self):
        """ Creates the <gmd:EX_GeographicBoundingBox> element
        
        Returns:
             ret_elem (_Element): The requested xml element
        """
        bbox = self.metadata.bounding_geometry
        if bbox is None:
            bbox = self.metadata.find_max_bounding_box()
        if bbox is None:
            raise ObjectDoesNotExist
        extent = bbox.extent

        ret_elem = Element(
            self.gmd + "EX_GeographicBoundingBox"
        )

        # gmd:extentTypeCode
        extent_type_code_elem = Element(
            self.gmd + "extentTypeCode",
            attrib={
                self.gco + "nilReason": "unknown"
            }
        )
        ret_elem.append(extent_type_code_elem)

        # gmd:westBoundingLongitude
        west_bound_elem = Element(
            self.gmd + "westBoundLongitude"
        )
        decimal_elem = Element(
            self.gco + "Decimal"
        )
        decimal_elem.text = str(extent[0])
        west_bound_elem.append(decimal_elem)
        ret_elem.append(west_bound_elem)

        # gmd:eastBoundingLongitude
        east_bound_elem = Element(
            self.gmd + "eastBoundLongitude"
        )
        decimal_elem = Element(
            self.gco + "Decimal"
        )
        decimal_elem.text = str(extent[2])
        east_bound_elem.append(decimal_elem)
        ret_elem.append(east_bound_elem)

        # gmd:southBoundingLongitude
        south_bound_elem = Element(
            self.gmd + "southBoundLatitude"
        )
        decimal_elem = Element(
            self.gco + "Decimal"
        )
        decimal_elem.text = str(extent[1])
        south_bound_elem.append(decimal_elem)
        ret_elem.append(south_bound_elem)

        # gmd:northBoundingLongitude
        north_bound_elem = Element(
            self.gmd + "northBoundLatitude"
        )
        decimal_elem = Element(
            self.gco + "Decimal"
        )
        decimal_elem.text = str(extent[3])
        north_bound_elem.append(decimal_elem)
        ret_elem.append(north_bound_elem)

        return ret_elem

    def _create_operation_metadata(self):
        """ Creates the <gmd:SV_OperationMetadata> element
        
        Returns:
             ret_elem (_Element): The requested xml element
        """

        ret_elem = Element(
            self.srv + "SV_OperationMetadata"
        )

        # self.srv:operationName
        operation_name_elem = Element(
            self.srv + "operationName"
        )
        char_str_elem = Element(
            self.gco + "CharacterString"
        )
        char_str_elem.text = "GetCapabilities"
        operation_name_elem.append(char_str_elem)
        ret_elem.append(operation_name_elem)

        # self.srv:DCP
        dcp_elem = Element(
            self.srv + "DCP"
        )
        dcp_list_elem = Element(
            self.srv + "DCPList",
            attrib={
                "codeList": "DCPList",
                "codeListValue": "WebService",
            }
        )
        dcp_elem.append(dcp_list_elem)
        ret_elem.append(dcp_elem)

        # self.srv:operationDescription
        operation_descr_elem = Element(
            self.srv + "operationDescription"
        )
        char_str_elem = Element(
            self.gco + "CharacterString"
        )
        char_str_elem.text = "Request the service capabilities document"
        operation_descr_elem.append(char_str_elem)
        ret_elem.append(operation_descr_elem)

        # self.srv:invocationName
        invocation_name_elem = Element(
            self.srv + "invocationName",
            attrib={
                self.gco + "nilReason": "unknown"
            }
        )
        ret_elem.append(invocation_name_elem)

        # self.srv:parameters
        parameters_elem = Element(
            self.srv + "parameters",
            attrib={
                self.gco + "nilReason": "unknown"
            }
        )
        ret_elem.append(parameters_elem)

        # self.srv:connectPoint
        connect_point_elem = Element(
            self.srv + "connectPoint"
        )
        connect_point_elem.append(self._create_online_resource())
        ret_elem.append(connect_point_elem)

        # self.srv:dependsOn
        depends_on_elem = Element(
            self.srv + "dependsOn",
            attrib={
                self.gco + "nilReason": "unknown"
            }
        )
        ret_elem.append(depends_on_elem)

        return ret_elem

    def _create_distribution_info(self):
        """ Creates the <gmd:distributionInfo> element

        Returns:
             ret_elem (_Element): The requested xml element
        """
        ret_elem = Element(
            self.gmd + "distributionInfo"
        )

        elem = Element(
            self.gmd + "MD_Distribution"
        )

        # gmd:distributionFormat
        distr_format_elem = Element(
            self.gmd + "distributionFormat"
        )
        distr_format_content_elem = self._create_distribution_format()
        distr_format_elem.append(distr_format_content_elem)
        elem.append(distr_format_elem)

        # gmd:distributor
        distributor_elem = Element(
            self.gmd + "distributor"
        )
        distributor_content_elem = self._create_distributor()
        distributor_elem.append(distributor_content_elem)
        elem.append(distributor_elem)

        # gmd:transferOptions
        transfer_options_elem = Element(
            self.gmd + "transferOptions"
        )
        transfer_options_elem.append(self._create_digital_transfer_options())
        elem.append(transfer_options_elem)

        xml_helper.add_subelement(ret_elem, elem)

        return ret_elem

    def _create_distribution_format(self):
        """ Creates the <gmd:MD_Format> element

        Returns:
             ret_elem (_Element): The requested xml element
        """


        ret_elem = Element(
            self.gmd + "MD_Format",
        )

        # gmd:name
        name_elem = Element(
            self.gmd + "name",
            attrib={
                self.gco + "nilReason": "inapplicable"
            }
        )
        ret_elem.append(name_elem)

        # gmd:version
        version_elem = Element(
            self.gmd + "version",
            attrib={
                self.gco + "nilReason": "inapplicable"
            }
        )
        ret_elem.append(version_elem)

        return ret_elem

    def _create_distributor(self):
        """ Creates the <gmd:MD_Distributor> element

        Returns:
             ret_elem (_Element): The requested xml element
        """


        ret_elem = Element(
            self.gmd + "MD_Distributor"
        )

        # gmd:distributorContact
        distributor_contact_elem = Element(
            self.gmd + "distributorContact"
        )
        distributor_contact_elem.append(self._create_contact())
        ret_elem.append(distributor_contact_elem)

        # gmd:distributionOrderProcess
        distribution_order_elem = Element(
            self.gmd + "distributionOrderProcess",
            attrib={
                self.gco + "nilReason": "unknown"
            }
        )
        ret_elem.append(distribution_order_elem)

        # gmd:distributorFormat
        distributor_format_elem = Element(
            self.gmd + "distributorFormat",
            attrib={
                self.gco + "nilReason": "unknown"
            }
        )
        ret_elem.append(distributor_format_elem)

        # gmd:distributorTransferOptions
        distributor_transfer_options_elem = Element(
            self.gmd + "distributorTransferOptions",
        )
        distributor_transfer_options_elem.append(self._create_digital_transfer_options())

        ret_elem.append(distributor_transfer_options_elem)

        return ret_elem

    def _create_digital_transfer_options(self):
        """ Creates the <gmd:MD_DigitalTransferOptions> element

        Returns:
             ret_elem (_Element): The requested xml element
        """

        ret_elem = Element(
            self.gmd + "MD_DigitalTransferOptions"
        )

        # gmd:unitsOfDistribution
        units_of_distribution_elem = Element(
            self.gmd + "unitsOfDistribution",
            attrib={
                self.gco + "nilReason": "unknown"
            }
        )
        ret_elem.append(units_of_distribution_elem)

        # gmd:transferSize
        transfer_size_elem = Element(
            self.gmd + "transferSize",
            attrib={
                self.gco + "nilReason": "unknown"
            }
        )
        ret_elem.append(transfer_size_elem)

        # gmd:onLine
        online_elem = Element(
            self.gmd + "onLine",
        )
        online_elem.append(self._create_online_resource())
        ret_elem.append(online_elem)

        # gmd:offLine
        offline_elem = Element(
            self.gmd + "offLine",
            attrib={
                self.gco + "nilReason": "unknown"
            }
        )
        ret_elem.append(offline_elem)

        return ret_elem

    def _create_data_quality_info(self):
        """ Creates the <gmd:dataQualityInfo> element

        Returns:
             ret_elem (_Element): The requested xml element
        """
        ret_elem = Element(
            self.gmd + "dataQualityInfo"
        )
        elem = Element(
            self.gmd + "DQ_DataQuality"
        )
        # gmd:scope
        scope_elem = Element(
            self.gmd + "scope"
        )
        scope_elem.append(self._create_scope())
        elem.append(scope_elem)

        # gmd:report
        legislation_groups = [
            "data_specifications",
            "metadata",
            "network_services",
        ]
        for legislation in self.regislations["inspire_rules"]:
            if legislation["group"] in legislation_groups \
                    and self.metadata_type in legislation["subject"]:
                if not self.use_legislation_amendment and '_amendment' in legislation["type"]:
                    # skip amendments if not desired
                    continue
                report_elem = Element(
                    self.gmd + "report"
                )
                report_elem.append(self._create_report(legislation))
                elem.append(report_elem)

        # gmd:lineage
        lineage_elem = Element(
            self.gmd + "lineage"
        )
        elem.append(lineage_elem)

        xml_helper.add_subelement(ret_elem, elem)

        return ret_elem

    def _create_scope(self):
        """ Creates the <gmd:DQ_Scope> element

        Returns:
             ret_elem (_Element): The requested xml element
        """
        ret_elem = Element(
            self.gmd + "DQ_Scope"
        )

        # gmd:level
        level_elem = Element(
            self.gmd + "level"
        )
        level_elem.append(self._create_hierarchy_level())
        ret_elem.append(level_elem)

        # gmd:extent
        extent_elem = Element(
            self.gmd + "extent"
        )
        extent_elem.append(self._create_extent_geographic())
        ret_elem.append(extent_elem)

        # gmd:levelDescription
        level_description_elem = Element(
            self.gmd + "levelDescription",
            attrib={
                self.gco + "nilReason": "unknown",
            }
        )
        ret_elem.append(level_description_elem)

        return ret_elem

    def _create_report(self, legislation, pass_val: bool=True):
        """ Creates the <gmd:DQ_DomainConsistency> element

        Returns:
             ret_elem (_Element): The requested xml element
        """
        ret_elem = Element(
            self.gmd + "DQ_DomainConsistency",
            attrib={
                self.xsi + "type": "gmd:DQ_DomainConsistency_Type",
            }
        )

        # gmd:result
        result_elem = Element(
            self.gmd + "result"
        )
        ret_elem.append(result_elem)

        # gmd:DQ_ConformanceResult
        dq_conformance_result_elem = Element(
            self.gmd + "DQ_ConformanceResult",
            attrib={
                self.xsi + "type": "gmd:DQ_ConformanceResult_Type",
            }
        )
        result_elem.append(dq_conformance_result_elem)

        # gmd:specification
        spec_elem = Element(
            self.gmd + "specification"
        )
        spec_elem.append(self._create_report_citation(legislation))
        dq_conformance_result_elem.append(spec_elem)

        # gmd:explanation
        explanation_elem = Element(
            self.gmd + "explanation"
        )
        char_str_elem = Element(
            self.gco + "CharacterString"
        )
        char_str_elem.text = "No explanation availabe"
        explanation_elem.append(char_str_elem)
        dq_conformance_result_elem.append(explanation_elem)

        # gmd:pass
        pass_elem = Element(
            self.gmd + "pass"
        )
        bool_elem = Element(
            self.gco + "Boolean"
        )

        # change the boolean to lower case to avoid conflict of a 'True'/'False' in other systems where 'true'/'false' is used
        bool_elem.text = str(pass_val).lower()
        pass_elem.append(bool_elem)
        dq_conformance_result_elem.append(pass_elem)

        return ret_elem

    def _create_report_citation(self, legislation):
        """ Creates the <gmd:CI_Citation> element for a report

        Returns:
             ret_elem (_Element): The requested xml element
        """
        ret_elem = Element(
            self.gmd + "CI_Citation"
        )

        # gmd:title
        title_elem = Element(
            self.gmd + "title"
        )
        char_str_elem = Element(
            self.gco + "CharacterString"
        )
        char_str_elem.text = legislation["label"]["de"]
        title_elem.append(char_str_elem)
        ret_elem.append(title_elem)

        # gmd:date
        code_list = "http://standards.iso.org/ittf/PubliclyAvailableStandards/ISO_19139_Schemas/resources/Codelist/ML_gmxCodelists.xml#CI_DateTypeCode"
        code_list_val = "publication"
        date_elem = Element(
            self.gmd + "date"
        )
        date_CI_date_elem = Element(
            self.gmd + "CI_Date"
        )
        date_CI_date_date_elem = Element(
            self.gmd + "date"
        )
        date_gco_elem = Element(
            self.gco + "Date"
        )
        date_gco_elem.text = legislation["date"]
        date_elem.append(date_CI_date_elem)
        date_CI_date_elem.append(date_CI_date_date_elem)
        date_CI_date_date_elem.append(date_gco_elem)
        ret_elem.append(date_elem)

        date_type_elem = Element(
            self.gmd + "dateType"
        )
        date_type_CI_elem = Element(
            self.gmd + "CI_DateTypeCode",
            attrib={
                "codeList": code_list,
                "codeListValue": code_list_val,
            }
        )
        date_type_CI_elem.text = code_list_val
        date_type_elem.append(date_type_CI_elem)
        ret_elem.append(date_type_elem)

        return ret_elem

    def overwrite_dataset_metadata(self, doc: str):
        """ Overwrites a dataset metadata document.

        Only overwrites elements, which can be modified using the Dataset Editor

        Args:
            doc (str): The document as string
        Returns:
             doc (str): The modified document
        """
        doc = xml_helper.parse_xml(doc)

        # Overwrite
        funcs = [
            self._overwrite_dataset_metadata_identification_form_info,
            self._overwrite_dataset_metadata_classification_form_info,
            self._overwrite_dataset_metadata_responsible_party_form_info,
            self._overwrite_dataset_metadata_spatial_extent_form_info,
            self._overwrite_dataset_metadata_licenses_form_info,
            self._overwrite_dataset_metadata_quality_form_info,
        ]
        for func in funcs:
            func(doc)

        doc = etree.tostring(doc, xml_declaration=True, encoding="utf-8", pretty_print=True)

        return doc

    def _overwrite_dataset_metadata_classification_form_info(self, doc: Element):
        """ Overwrites the elements according to the Dataset Classification Form.

        Args:
            doc (Etree): The document as etree
        Returns:

        """
        ident_elem = xml_helper.try_get_single_element_from_xml("//" + GENERIC_NAMESPACE_TEMPLATE.format("MD_DataIdentification"), doc)

        # Overwrite keyword elements
        ## Remove existing elements
        existing_keyword_elems = xml_helper.try_get_element_from_xml("//" + GENERIC_NAMESPACE_TEMPLATE.format("descriptiveKeywords"), ident_elem)
        for kw in existing_keyword_elems:
            xml_helper.remove_element(kw)
        ## Add new
        descr_keywords_elem = self._create_keywords()
        xml_helper.add_subelement(ident_elem, descr_keywords_elem, after=GENERIC_NAMESPACE_TEMPLATE.format("pointOfContact"))

        # Overwrite topic category elements
        ## Remove existing elements
        existing_category_elems = xml_helper.try_get_element_from_xml("//" + GENERIC_NAMESPACE_TEMPLATE.format("topicCategory"), ident_elem)
        for cat in existing_category_elems:
            xml_helper.remove_element(cat)
        ## Add new
        topic_category_elems = self._create_topic_category()
        for elem in topic_category_elems:
            xml_helper.add_subelement(ident_elem, elem, after=GENERIC_NAMESPACE_TEMPLATE.format("language"))

    def _overwrite_dataset_metadata_identification_form_info(self, doc: Element):
        """ Overwrites the elements according to the Dataset Identification Form.

        Args:
            doc (Etree): The document as etree
        Returns:

        """
        root = doc.getroot()
        # Overwrite language
        lang_elem = xml_helper.try_get_single_element_from_xml("//" + GENERIC_NAMESPACE_TEMPLATE.format("LanguageCode"), root)
        xml_helper.write_attribute(lang_elem, attrib="codeListValue", txt=self.described_resource.language_code)
        xml_helper.write_text_to_element(lang_elem, txt=self.described_resource.language_code)

        # Overwrite encoding
        encoding_elem = xml_helper.try_get_single_element_from_xml("//" + GENERIC_NAMESPACE_TEMPLATE.format("MD_CharacterSetCode"), root)
        xml_helper.write_attribute(encoding_elem, attrib="codeListValue", txt=self.described_resource.character_set_code)

        # Overwrite dateStamp
        date_stamp_elem = xml_helper.try_get_single_element_from_xml("//" + GENERIC_NAMESPACE_TEMPLATE.format("dateStamp"), root)
        xml_helper.write_text_to_element(date_stamp_elem, ".//" + GENERIC_NAMESPACE_TEMPLATE.format("Date"), self.described_resource.date_stamp.strftime(DATE_STRF))

        ident_elem = xml_helper.try_get_single_element_from_xml("//" + GENERIC_NAMESPACE_TEMPLATE.format("identificationInfo"), root)

        # Overwrite title
        title_elem = xml_helper.try_get_single_element_from_xml(".//" + GENERIC_NAMESPACE_TEMPLATE.format("title"), ident_elem)
        xml_helper.write_text_to_element(title_elem, "./" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString"), self.metadata.title)

        # Overwrite abstract
        abstract_elem = xml_helper.try_get_single_element_from_xml(".//" + GENERIC_NAMESPACE_TEMPLATE.format("abstract"), ident_elem)
        xml_helper.write_text_to_element(abstract_elem, "./" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString", self.metadata.abstract))

        # Overwrite reference systems
        ## First remove old onces
        existing_ref_system_elems = xml_helper.try_get_element_from_xml("//" + GENERIC_NAMESPACE_TEMPLATE.format("referenceSystemInfo"), root)
        for elem in existing_ref_system_elems:
            xml_helper.remove_element(elem)
        ## Then create new
        new_ref_system_elems = self._create_reference_system_info()
        for elem in new_ref_system_elems:
            xml_helper.add_subelement(root, elem, after=GENERIC_NAMESPACE_TEMPLATE.format("dateStamp"))

    def _overwrite_dataset_metadata_responsible_party_form_info(self, doc: Element):
        """ Overwrites the elements according to the Dataset Responsible Party Form.

        Args:
            doc (Etree): The document as etree
        Returns:

        """
        root = doc.getroot()

        # Remove existing contact information elem
        contact_info_elems = xml_helper.try_get_element_from_xml("//" + GENERIC_NAMESPACE_TEMPLATE.format("contact"), root)
        for elem in contact_info_elems:
            xml_helper.remove_element(elem)

        # Add new elements
        ## Contact info are available on first level and nested inside of gmd:MD_DataIdentification
        contact_elem = self._create_contact()
        xml_helper.add_subelement(root, contact_elem, after=GENERIC_NAMESPACE_TEMPLATE.format("hierarchyLevel"))

        ident_elem = xml_helper.try_get_single_element_from_xml("//" + GENERIC_NAMESPACE_TEMPLATE.format("MD_DataIdentification"), root)
        point_of_contact_elem = Element(
            self.gmd + "pointOfContact"
        )
        # _create_contact() returns the <gmd:contact> wrapping element, which is not needed here.
        # We continue using the inner <gmd:CI_ResponsibleParty>
        copy_contact_elem = copy(contact_elem)
        point_of_contact_elem.append(
            xml_helper.try_get_single_element_from_xml("./" + GENERIC_NAMESPACE_TEMPLATE.format("CI_ResponsibleParty"), copy_contact_elem)
        )
        xml_helper.add_subelement(ident_elem, point_of_contact_elem, after=GENERIC_NAMESPACE_TEMPLATE.format("abstract"))


    def _overwrite_dataset_metadata_spatial_extent_form_info(self, doc: Element):
        """ Overwrites the elements according to the Dataset Spatial Extent Form.

        Args:
            doc (Etree): The document as etree
        Returns:

        """
        pass

    def _overwrite_dataset_metadata_licenses_form_info(self, doc: Element):
        """ Overwrites the elements according to the Dataset Licenses/Constraints Form.

        Args:
            doc (Etree): The document as etree
        Returns:

        """
        pass

    def _overwrite_dataset_metadata_quality_form_info(self, doc: Element):
        """ Overwrites the elements according to the Dataset Quality Form.

        Args:
            doc (Etree): The document as etree
        Returns:

        """
        pass