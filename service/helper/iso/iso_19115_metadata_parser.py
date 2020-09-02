"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 04.07.2019

"""
import json
import urllib
import uuid
from django.utils import timezone

from dateutil.parser import parse
from django.contrib.gis.geos import Polygon
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.db import transaction
from django.utils.timezone import utc
from lxml.etree import _Element, Element

from MrMap.settings import XML_NAMESPACES, GENERIC_NAMESPACE_TEMPLATE
from service.settings import INSPIRE_LEGISLATION_FILE, HTML_METADATA_URI_TEMPLATE, SERVICE_METADATA_URI_TEMPLATE, \
    SERVICE_DATASET_URI_TEMPLATE
from MrMap import utils
from service.helper import xml_helper
from service.helper.common_connector import CommonConnector
from service.helper.enums import ConnectionEnum, MetadataEnum, DocumentEnum, ResourceOriginEnum
from service.helper.epsg_api import EpsgApi
from service.models import Metadata, Keyword, Document, Dataset, LegalDate, LegalReport
from structure.models import Organization, MrMapGroup


class ISOMetadata:
    def __init__(self, uri: str, origin: str = ResourceOriginEnum.CAPABILITIES.value):
        self.section = "all" # serviceIdentification, serviceProvider, operationMetadata, contents, all

        self.uri = uri
        self.raw_metadata = None

        self.character_set_code = None
        self.md_standard_name = None
        self.md_standard_version = None

        # referenced from mapbender metadata parsing
        self.file_identifier = None
        self.date_stamp = None
        self.dataset_id = None
        self.dataset_id_code_space = None
        self.last_change_date = None
        self.hierarchy_level = None
        self.title = None
        self.abstract = None
        self.keywords = []
        self.language = None
        self.iso_categories = []
        self.formats = []
        self.download_link = None
        self.transfer_size = None
        self.preview_image = None
        self.bounding_box = {
            "min_x": None,
            "min_y": None,
            "max_x": None,
            "max_y": None,
        }

        self.polygonal_extent_exterior = []
        self.tmp_extent_begin = None
        self.tmp_extent_end = None

        self.spatial_res_val = None
        self.spatial_res_type = None
        self.ground_resolution = None
        self.ref_system = None
        self.ref_system_version = None
        self.ref_system_authority = None
        self.lineage = None

        self.use_limitation = None

        self.distribution_function = None
        self.fraction_denominator = None

        self.legal_dates = []
        self.legal_reports = []

        self.license_source_note = None
        self.license_json = None
        self.fees = None

        self.access_constraints = None
        self.responsible_party = None
        self.contact_email = None
        self.contact_phone = None
        self.contact_person = None
        self.update_frequency = None
        self.valid_update_frequencies = [
            'continual',
            'daily',
            'weekly',
            'fortnightly',
            'monthly',
            'quarterly',
            'biannually',
            'annually',
            'asNeeded',
            'irregular',
            'notPlanned',
            'unknown'
        ]

        self.inspire_interoperability = True
        self.interoperability_list = []
        self.origin = origin

        self.is_broken = False

        XML_NAMESPACES["gmd"] = "http://www.isotc211.org/2005/gmd"
        XML_NAMESPACES["gco"] = "http://www.isotc211.org/2005/gco"
        XML_NAMESPACES["gml"] = "http://www.opengis.net/gml"
        XML_NAMESPACES["srv"] = "http://www.isotc211.org/2005/srv"
        XML_NAMESPACES["xlink"] = "http://www.w3.org/1999/xlink"
        XML_NAMESPACES["xsi"] = "http://www.w3.org/2001/XMLSchema-instance"
        XML_NAMESPACES["inspire_common"] = "http://inspire.ec.europa.eu/schemas/common/1.0"
        XML_NAMESPACES["inspire_vs"] = "http://inspire.ec.europa.eu/schemas/inspire_vs/1.0"

        # load uri and start parsing
        self.get_metadata()
        self.parse_xml()

        # check for validity
        # we expect that at least title and file_identifier exist
        MIN_REQUIRED_ISO_MD = [
            self.file_identifier,
            self.title,
        ]
        for attr in MIN_REQUIRED_ISO_MD:
            if attr is None:
                self.is_broken = True

    def get_metadata(self):
        """ Start a network call to retrieve the original capabilities xml document.

        Using the connector class, this function will GET the capabilities xml document as string.
        No file will be downloaded and stored on the storage. The string will be stored in the OGCWebService instance.

        Returns:
             nothing
        """
        ows_connector = CommonConnector(
            url=self.uri,
            external_auth=None,
            connection_type=ConnectionEnum.REQUESTS
        )
        ows_connector.http_method = 'GET'
        ows_connector.load()
        if ows_connector.status_code != 200:
            raise ConnectionError(ows_connector.status_code)

        self.raw_metadata = ows_connector.content.decode("UTF-8")

    def _parse_xml_dataset_id(self, xml_obj: _Element, xpath_type: str):
        """ Parse the dataset id and it's code space from the metadata xml

        Args:
            xml_obj (_Element): The xml element
            xpath_type (str): The element identificator which is determined by SV_ServiceIdentification or MD_DataIdentification
        Returns:
            nothing
        """
        # First check if MD_Identifier is set, then check if RS_Identifier is used!
        # Initialize datasetid
        self.dataset_id = 'undefined'
        code = xml_helper.try_get_text_from_xml_element(elem='//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:citation/gmd:CI_Citation/gmd:identifier/gmd:MD_Identifier/gmd:code/gco:CharacterString'.format(xpath_type), xml_elem=xml_obj)
        if code is not None and len(code) != 0:
            # new implementation:
            # http://inspire.ec.europa.eu/file/1705/download?token=iSTwpRWd&usg=AOvVaw18y1aTdkoMCBxpIz7tOOgu
            # from 2017-03-02 - the MD_Identifier - see C.2.5 Unique resource identifier - it is separated with a slash - the codespace should be everything after the last slash
            # now try to check if a single slash is available and if the md_identifier is a url
            parsed_url = urllib.parse.urlsplit(code)
            if parsed_url.scheme == "http" or parsed_url.scheme == "https" and "/" in parsed_url.path:
                tmp = code.split("/")
                self.dataset_id = tmp[len(tmp) - 1]
                self.dataset_id_code_space = code.replace(self.dataset_id, "")
            elif parsed_url.scheme == "http" or parsed_url.scheme == "https" and "#" in code:
                tmp = code.split("#")
                self.dataset_id = tmp[1]
                self.dataset_id_code_space = tmp[0]
            else:
                self.dataset_id = code
                self.dataset_id_code_space = ""
        else:
            # try to read code from RS_Identifier
            code = xml_helper.try_get_text_from_xml_element(elem='//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:citation/gmd:CI_Citation/gmd:identifier/gmd:RS_Identifier/gmd:code/gco:CharacterString'.format(xpath_type), xml_elem=xml_obj)
            code_space = xml_helper.try_get_text_from_xml_element(elem="//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:citation/gmd:CI_Citation/gmd:identifier/gmd:RS_Identifier/gmd:codeSpace/gco:CharacterString".format(xpath_type), xml_elem=xml_obj)
            if code_space is not None and code is not None and len(code_space) > 0 and len(code) > 0:
                self.dataset_id = code
                self.dataset_id_code_space = code_space
            else:
                self.is_broken = True

    def _parse_xml_polygons(self, xml_obj: _Element, xpath_type: str):
        """ Parse the polygon information from the xml document

        Args:
            xml_obj (_Element): The xml element
            xpath_type (str): The element identificator which is determined by SV_ServiceIdentification or MD_DataIdentification
        Returns:
             nothing
        """
        polygons = xml_helper.try_get_element_from_xml(xml_elem=xml_obj, elem='//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:extent/gmd:EX_Extent/gmd:geographicElement/gmd:EX_BoundingPolygon/gmd:polygon/gml:MultiSurface'.format(xpath_type))
        if len(polygons) > 0:
            surface_elements = xml_helper.try_get_element_from_xml(xml_elem=xml_obj, elem="//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:extent/gmd:EX_Extent/gmd:geographicElement/gmd:EX_BoundingPolygon/gmd:polygon/gml:MultiSurface/gml:surfaceMember".format(xpath_type))
            for element in surface_elements:
                self.polygonal_extent_exterior.append(self.parse_polygon(element))
        else:
            polygons = xml_helper.try_get_text_from_xml_element(xml_obj, '//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:extent/gmd:EX_Extent/gmd:geographicElement/gmd:EX_BoundingPolygon/gmd:polygon/gml:Polygon'.format(xpath_type))
            if polygons is not None:
                polygon = xml_helper.try_get_single_element_from_xml(xml_elem=xml_obj, elem="//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:extent/gmd:EX_Extent/gmd:geographicElement/gmd:EX_BoundingPolygon/gmd:polygon".format(xpath_type))
                self.polygonal_extent_exterior.append(self.parse_polygon(polygon))
            else:
                self.polygonal_extent_exterior.append(self.parse_bbox(self.bounding_box))

    def _parse_xml_legal_dates(self, xml_obj: Element):
        """ Parses existing CI_Date elements from the MD_DataIdentification element

        Args:
            xml_obj (Element): The document xml element
        Returns:

        """
        md_data_ident_elem = xml_helper.try_get_single_element_from_xml(
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("MD_DataIdentification"),
            xml_obj
        )
        legal_date_elems = xml_helper.try_get_element_from_xml(
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("CI_Date"),
            md_data_ident_elem
        )
        for legal_date_elem in legal_date_elems:
            legal_date = LegalDate()
            legal_date.date = xml_helper.try_get_text_from_xml_element(
                legal_date_elem,
                ".//" + GENERIC_NAMESPACE_TEMPLATE.format("Date")
            )
            legal_date.date_type_code = xml_helper.try_get_attribute_from_xml_element(
                legal_date_elem,
                "codeListValue",
                ".//" + GENERIC_NAMESPACE_TEMPLATE.format("CI_DateTypeCode")
            )
            legal_date.date_type_code_list_url = xml_helper.try_get_attribute_from_xml_element(
                legal_date_elem,
                "codeList",
                ".//" + GENERIC_NAMESPACE_TEMPLATE.format("CI_DateTypeCode")
            )
            self.legal_dates.append(legal_date)

    def _parse_xml_legal_reports(self, xml_obj: Element):
        """ Parses existing CI_Date elements from the MD_DataIdentification element

        Args:
            xml_obj (Element): The document xml element
        Returns:

        """
        data_quality_elem = xml_helper.try_get_single_element_from_xml(
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("DQ_DataQuality"),
            xml_obj
        )
        report_elems = xml_helper.try_get_single_element_from_xml(
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("report"),
            xml_obj
        )
        for report_elem in report_elems:
            report = LegalReport()
            report.title = xml_helper.try_get_text_from_xml_element(
                report_elem,
                ".//" + GENERIC_NAMESPACE_TEMPLATE.format("title") + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
            )
            report.explanation = xml_helper.try_get_text_from_xml_element(
                report_elem,
                ".//" + GENERIC_NAMESPACE_TEMPLATE.format("explanation") + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
            )
            legal_date = LegalDate()
            legal_date.date = xml_helper.try_get_text_from_xml_element(
                report_elem,
                ".//" + GENERIC_NAMESPACE_TEMPLATE.format("Date")
            )
            legal_date.date_type_code = xml_helper.try_get_attribute_from_xml_element(
                report_elem,
                "codeListValue",
                ".//" + GENERIC_NAMESPACE_TEMPLATE.format("CI_DateTypeCode")
            )
            legal_date.date_type_code_list_url = xml_helper.try_get_attribute_from_xml_element(
                report_elem,
                "codeList",
                ".//" + GENERIC_NAMESPACE_TEMPLATE.format("CI_DateTypeCode")
            )
            report.date = legal_date
            self.legal_reports.append(report)

    def parse_xml(self):
        """ Reads the needed data from the xml and writes to an ISOMetadata instance (self)

        Returns:
             nothing
        """
        xml = self.raw_metadata
        xml_obj = xml_helper.parse_xml(xml)
        self.file_identifier = xml_helper.try_get_text_from_xml_element(xml_obj, "//gmd:MD_Metadata/gmd:fileIdentifier/gco:CharacterString")
        self.character_set_code = xml_helper.try_get_attribute_from_xml_element(xml_elem=xml_obj, attribute="codeListValue", elem="//gmd:MD_Metadata/gmd:characterSet/gmd:MD_CharacterSetCode")
        if self.file_identifier is None:
            self.file_identifier = uuid.uuid4()
        self.date_stamp = xml_helper.try_get_text_from_xml_element(xml_obj, "//gmd:MD_Metadata/gmd:dateStamp/gco:Date")
        self.last_change_date = xml_helper.try_get_text_from_xml_element(xml_obj, "//gmd:MD_Metadata/gmd:dateStamp/gco:Date")

        self.md_standard_name = xml_helper.try_get_text_from_xml_element(xml_obj, "//gmd:metadataStandardName/gco:CharacterString")
        self.md_standard_version = xml_helper.try_get_text_from_xml_element(xml_obj, "//gmd:metadataStandardVersion/gco:CharacterString")

        self._parse_xml_legal_dates(xml_obj)
        self._parse_xml_legal_reports(xml_obj)

        # try to transform the last_change_date into a datetime object
        try:
            self.last_change_date = parse(self.last_change_date, tzinfo=timezone.utc)
        except (ValueError, OverflowError, TypeError):
            # if this is not possible due to wrong input, just use the current time...
            self.last_change_date = timezone.now()

        self.hierarchy_level = xml_helper.try_get_attribute_from_xml_element(xml_obj, "codeListValue", "//gmd:MD_Metadata/gmd:hierarchyLevel/gmd:MD_ScopeCode")
        if self.hierarchy_level == "service":
            xpath_type = "srv:SV_ServiceIdentification"
        else:
            xpath_type = "gmd:MD_DataIdentification"
        self.title = xml_helper.try_get_text_from_xml_element(xml_obj, "//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:citation/gmd:CI_Citation/gmd:title/gco:CharacterString".format(xpath_type))
        self._parse_xml_dataset_id(xml_obj, xpath_type)
        self.abstract = xml_helper.try_get_text_from_xml_element(xml_obj, "//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:abstract/gco:CharacterString".format(xpath_type))
        keywords = xml_helper.try_get_element_from_xml(xml_elem=xml_obj, elem="//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:descriptiveKeywords/gmd:MD_Keywords/gmd:keyword/gco:CharacterString".format(xpath_type))
        for keyword in keywords:
            if keyword.text is not None and keyword not in self.keywords:
                self.keywords.append(xml_helper.try_get_text_from_xml_element(keyword))

        language = xml_helper.try_get_single_element_from_xml(xml_elem=xml_obj,
                                                        elem="//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:language/gmd:LanguageCode".format(
                                                           xpath_type))
        if language.text is not None:
            self.language = xml_helper.try_get_text_from_xml_element(language)

        iso_categories = xml_helper.try_get_element_from_xml(xml_elem=xml_obj, elem="//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:topicCategory/gmd:MD_TopicCategoryCode".format(xpath_type))
        for iso_category in iso_categories:
            self.iso_categories.append(xml_helper.try_get_text_from_xml_element(iso_category))

        # Get all values from <gmd:distributionInfo> which declares the distributionFormat
        formats = xml_helper.try_get_element_from_xml(xml_elem=xml_obj, elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("distributionFormat"))
        for format_elem in formats:
            # get the character value per format
            name_elem = xml_helper.try_get_single_element_from_xml(xml_elem=format_elem, elem=".//" + GENERIC_NAMESPACE_TEMPLATE.format("name"))
            if name_elem is None:
                continue
            val = xml_helper.try_get_text_from_xml_element(xml_elem=name_elem, elem=".//" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString"))
            self.formats.append(val)

        self.download_link = xml_helper.try_get_text_from_xml_element(xml_obj, '//gmd:MD_Metadata/gmd:distributionInfo/gmd:MD_Distribution/gmd:transferOptions/gmd:MD_DigitalTransferOptions/gmd:onLine/gmd:CI_OnlineResource[gmd:function/gmd:CI_OnLineFunctionCode/@codeListValue="download"]/gmd:linkage/gmd:URL')
        self.transfer_size = xml_helper.try_get_text_from_xml_element(xml_obj, '//gmd:MD_Metadata/gmd:distributionInfo/gmd:MD_Distribution/gmd:transferOptions/gmd:MD_DigitalTransferOptions/gmd:transferSize/gco:Real')
        self.preview_image = xml_helper.try_get_text_from_xml_element(xml_obj, "//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:graphicOverview/gmd:MD_BrowseGraphic/gmd:fileName/gco:CharacterString".format(xpath_type))
        try:
            self.bounding_box["min_x"] = float(xml_helper.try_get_text_from_xml_element(xml_obj, "//gmd:westBoundLongitude/gco:Decimal".format(xpath_type)))
            self.bounding_box["min_y"] = float(xml_helper.try_get_text_from_xml_element(xml_obj, "//gmd:southBoundLatitude/gco:Decimal".format(xpath_type)))
            self.bounding_box["max_x"] = float(xml_helper.try_get_text_from_xml_element(xml_obj, "//gmd:eastBoundLongitude/gco:Decimal".format(xpath_type)))
            self.bounding_box["max_y"] = float(xml_helper.try_get_text_from_xml_element(xml_obj, "//gmd:northBoundLatitude/gco:Decimal".format(xpath_type)))
        except TypeError:
            self.bounding_box = None

        self._parse_xml_polygons(xml_obj, xpath_type)

        self.tmp_extent_begin = xml_helper.try_get_text_from_xml_element(xml_obj, "//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:extent/gmd:EX_Extent/gmd:temporalElement/gmd:EX_TemporalExtent/gmd:extent/gml:TimePeriod/gml:beginPosition".format(xpath_type))
        if self.tmp_extent_begin is None:
            self.tmp_extent_begin = "1900-01-01"

        self.tmp_extent_end = xml_helper.try_get_text_from_xml_element(xml_obj, "//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:extent/gmd:EX_Extent/gmd:temporalElement/gmd:EX_TemporalExtent/gmd:extent/gml:TimePeriod/gml:endPosition".format(xpath_type))
        if self.tmp_extent_end is None:
            self.tmp_extent_end = "1900-01-01"

        equivalent_scale = xml_helper.try_get_text_from_xml_element(xml_obj, "//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:spatialResolution/gmd:MD_Resolution/gmd:equivalentScale/gmd:MD_RepresentativeFraction/gmd:denominator/gco:Integer".format(xpath_type))
        ground_res = xml_helper.try_get_text_from_xml_element(xml_obj, "//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:spatialResolution/gmd:MD_Resolution/gmd:distance/gco:Distance".format(xpath_type))
        if equivalent_scale is not None and int(equivalent_scale) > 0:
            self.spatial_res_val = equivalent_scale
            self.spatial_res_type = "scaleDenominator"
        elif ground_res is not None and len(ground_res) > 0:
            self.spatial_res_val = ground_res
            self.spatial_res_type = "groundDistance"

        self.ref_system = xml_helper.try_get_text_from_xml_element(xml_obj, "//gmd:MD_Metadata/gmd:referenceSystemInfo/gmd:MD_ReferenceSystem/gmd:referenceSystemIdentifier/gmd:RS_Identifier/gmd:code/gco:CharacterString")
        self.ref_system_version = xml_helper.try_get_text_from_xml_element(xml_obj, "//gmd:MD_Metadata/gmd:referenceSystemInfo/gmd:MD_ReferenceSystem/gmd:referenceSystemIdentifier/gmd:RS_Identifier/gmd:version/gco:CharacterString")
        self.ref_system_authority = xml_helper.try_get_text_from_xml_element(xml_obj, "//gmd:MD_Metadata/gmd:referenceSystemInfo/gmd:MD_ReferenceSystem/gmd:referenceSystemIdentifier/gmd:RS_Identifier/gmd:authority/gmd:CI_Citation/gmd:title/gco:CharacterString")
        epsg_api = EpsgApi()
        if self.ref_system is not None:
            self.ref_system = "EPSG:{}".format(epsg_api.get_subelements(self.ref_system).get("code"))

        # gmd:CI_OnLineFunctionCode
        dist_func_elem = xml_helper.try_get_single_element_from_xml("//" + GENERIC_NAMESPACE_TEMPLATE.format("CI_OnLineFunctionCode"), xml_obj)
        self.distribution_function = xml_helper.try_get_attribute_from_xml_element(
            dist_func_elem,
            "codeListValue",
        )
        del dist_func_elem

        # gmd:MD_RepresentativeFraction
        fraction_elem = xml_helper.try_get_single_element_from_xml("//" + GENERIC_NAMESPACE_TEMPLATE.format("MD_RepresentativeFraction"), xml_obj)
        self.fraction_denominator = xml_helper.try_get_text_from_xml_element(fraction_elem, ".//" + GENERIC_NAMESPACE_TEMPLATE.format("Integer"))
        del fraction_elem

        # gmd:useLimitation
        limit_elem = xml_helper.try_get_single_element_from_xml("//" + GENERIC_NAMESPACE_TEMPLATE.format("useLimitation"), xml_obj)
        self.use_limitation = xml_helper.try_get_text_from_xml_element(limit_elem, ".//" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString"))
        del limit_elem

        self.lineage = xml_helper.try_get_text_from_xml_element(xml_obj, "//gmd:MD_Metadata/gmd:dataQualityInfo/gmd:DQ_DataQuality/gmd:lineage/gmd:LI_Lineage/gmd:statement/gco:CharacterString")

        restriction_code_attr_val = xml_helper.try_get_element_from_xml(xml_elem=xml_obj, elem='//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:resourceConstraints/gmd:MD_LegalConstraints/gmd:useConstraints/gmd:MD_RestrictionCode/@codeListValue'.format(xpath_type))
        if len(restriction_code_attr_val) >= 2:
            legal_constraints = ""
            if restriction_code_attr_val[0] == 'license' and restriction_code_attr_val[1] == 'otherRestrictions':
                other_constraints = xml_helper.try_get_element_from_xml(xml_elem=xml_obj, elem='//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:resourceConstraints/gmd:MD_LegalConstraints[gmd:useConstraints/gmd:MD_RestrictionCode/@codeListValue="otherRestrictions"]/gmd:otherConstraints/gco:CharacterString'.format(xpath_type))
                for constraint in other_constraints:
                    try:
                        tmp_constraint = xml_helper.try_get_text_from_xml_element(xml_elem=constraint)
                        constraint_json = json.loads(tmp_constraint)
                        self.license_source_note = constraint_json.get("quelle", None)
                        self.license_json = constraint_json
                    except ValueError:
                        # no, this is not a json!
                        # handle it is a normal text
                        legal_constraints += tmp_constraint + ";"
            self.fees = legal_constraints

        self.access_constraints = xml_helper.try_get_text_from_xml_element(xml_obj, '//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:resourceConstraints/gmd:MD_LegalConstraints[gmd:accessConstraints/gmd:MD_RestrictionCode/@codeListValue="otherRestrictions"]/gmd:otherConstraints/gco:CharacterString'.format(xpath_type))
        self.responsible_party = xml_helper.try_get_text_from_xml_element(xml_obj, '//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:pointOfContact/gmd:CI_ResponsibleParty/gmd:organisationName/gco:CharacterString'.format(xpath_type))
        self.contact_person = xml_helper.try_get_text_from_xml_element(xml_obj, '//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:pointOfContact/gmd:CI_ResponsibleParty/gmd:individualName/gco:CharacterString'.format(xpath_type))
        self.contact_phone = xml_helper.try_get_text_from_xml_element(xml_obj, '//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:pointOfContact/gmd:CI_ResponsibleParty/gmd:contactInfo/gmd:CI_Contact/gmd:phone/gmd:CI_Telephone/gmd:voice/gco:CharacterString'.format(xpath_type))
        self.contact_email = xml_helper.try_get_text_from_xml_element(xml_obj, '//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:pointOfContact/gmd:CI_ResponsibleParty/gmd:contactInfo/gmd:CI_Contact/gmd:address/gmd:CI_Address/gmd:electronicMailAddress/gco:CharacterString'.format(xpath_type))
        update_frequency = xml_helper.try_get_attribute_from_xml_element(xml_elem=xml_obj, attribute="codeListValue", elem='//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:resourceMaintenance/gmd:MD_MaintenanceInformation/gmd:maintenanceAndUpdateFrequency/gmd:MD_MaintenanceFrequencyCode'.format(xpath_type))
        if update_frequency in self.valid_update_frequencies:
            self.update_frequency = update_frequency

        # inspire regulations
        regislations = {
            "inspire_rules": []
        }
        with open(INSPIRE_LEGISLATION_FILE, "r", encoding="utf-8") as _file:
            regislations = json.load(_file)
        for regislation in regislations["inspire_rules"]:
            reg = {
                "name": regislation.get("name", None),
                "date": regislation.get("date", "1900-01-01"),
                "pass": None,
            }
            statement = xml_helper.try_get_text_from_xml_element(xml_obj, '//gmd:MD_Metadata/gmd:dataQualityInfo/gmd:DQ_DataQuality/gmd:report/gmd:DQ_DomainConsistency/gmd:result/gmd:DQ_ConformanceResult[gmd:specification/gmd:CI_Citation/gmd:title/gco:CharacterString="{}" and gmd:specification/gmd:CI_Citation/gmd:date/gmd:CI_Date/gmd:date/gco:Date="{}"]/gmd:pass/gco:Boolean'.format(reg["name"], reg["date"]))
            statement_val = utils.resolve_boolean_attribute_val(statement)
            if statement_val is None:
                reg["pass"] = "not declared"
                self.inspire_interoperability = False
            else:
                reg["pass"] = statement_val
                # if only one regislation is not fullfilled, we do not have interoperability
                if not statement_val:
                    self.inspire_interoperability = False
            self.interoperability_list.append(reg)

    def parse_bbox(self, bbox: dict):
        """ Creates a Polygon object from a bbox

        Args:
            bbox (dict): The bbox as dict
        Returns:
             polygon (Polygon): The polygon object
        """
        polygon = Polygon()
        if bbox is not None:
            bounding_points = (
                (bbox["min_x"], bbox["min_y"]),
                (bbox["min_x"], bbox["max_y"]),
                (bbox["max_x"], bbox["max_y"]),
                (bbox["max_x"], bbox["min_y"]),
                (bbox["min_x"], bbox["min_y"])
            )
            polygon = Polygon(bounding_points)
        return polygon

    def parse_polygon(self, polygon_elem):
        """ Creates points from continuous polygon points array

        Args:
            polygon: The etree xml element which holds the polygons
        Returns:
             polygon (Polygon): The polygon object created from the data
        """
        relative_ring_xpath = "./gml:Polygon/gml:exterior/gml:LinearRing/gml:posList"
        relative_coordinate_xpath = "./gml:Polygon/gml:exterior/gml:LinearRing/gml:coordinates"
        pos_list = xml_helper.try_get_element_from_xml(xml_elem=polygon_elem, elem=relative_ring_xpath)
        min_x = 10000
        max_x = 0
        min_y = 100000
        max_y = 0
        if len(pos_list) > 0:
            exterior_ring_points = xml_helper.try_get_text_from_xml_element(xml_elem=polygon_elem, elem=relative_ring_xpath)
            if len(exterior_ring_points) > 0:
                # posList is only space separated
                points_list = exterior_ring_points.split(" ")
                inner_points = ()
                for i in range(int(len(points_list) / 2) - 1):
                    x = float(points_list[2 * i])
                    y = float(points_list[(2 * i) + 1])
                    if x < min_x:
                        min_x = x
                    if x > max_x:
                        max_x = x
                    if y < min_y:
                        min_y = y
                    if y > max_y:
                        max_y = y
                    p = ((x, y),)
                    inner_points = (inner_points) + p
        else:
            # try to read coordinates
            exterior_ring_points = xml_helper.try_get_text_from_xml_element(xml_elem=polygon_elem, elem=relative_coordinate_xpath)
            # two coordinates of one point are comma separated
            # problems with ', ' or ' ,' -> must be deleted before
            exterior_ring_points = exterior_ring_points.replace(', ', ',').replace(' ,', ',')
            points_list = exterior_ring_points.split(" ")
            inner_points = ()
            for point in points_list:
                point = point.split[","]
                x = float(points_list[0])
                y = float(points_list[1])
                if x < min_x:
                    min_x = x
                if x > max_x:
                    max_x = x
                if y < min_y:
                    min_y = y
                if y > max_y:
                    max_y = y
                p = ((x, y),)
                inner_points = (inner_points) + p
        bounding_points = ((min_x, min_y), (min_x, max_y), (max_x, max_y), (max_x, min_y), (min_x, min_y))
        if inner_points[0] != inner_points[len(inner_points)-1]:
            # polygon is not closed!
            inner_points = inner_points + (inner_points[0],)
        polygon = Polygon(bounding_points, inner_points)
        return polygon

    @transaction.atomic
    def to_db_model(self, type=MetadataEnum.DATASET.value, created_by: MrMapGroup = None):
        """ Get corresponding metadata object from database or create it if not found!

        Returns:
            metadata (Metadata): A db model Metadata object
        """
        update = False
        new = False
        # try to find the object by uuid and uri. If not existing yet, create a new record
        try:
            metadata = Metadata.objects.get(identifier=self.file_identifier, metadata_url=self.uri)
            # check if the parsed metadata might be newer
            # make sure both date time objects will be comparable
            persisted_change = metadata.last_remote_change.replace(tzinfo=utc)
            new_change = self.last_change_date.replace(tzinfo=utc)
            if persisted_change > new_change:
                # Nothing to do here
                return metadata
            else:
                update = True
        except ObjectDoesNotExist:
            # object does not seem to exist -> create it!
            metadata = Metadata()
            md_type = type
            metadata.metadata_type = md_type
            if metadata.is_dataset_metadata:
                metadata.dataset = Dataset()
                metadata.dataset.created_by = created_by
            metadata.created_by = created_by
            new = True

        if update or new:

            # In case of a dataset, we need to fill the information into the dataset object
            if metadata.is_dataset_metadata:
                metadata.dataset = self._fill_dataset_db_model(metadata.dataset)

            metadata = self._fill_metadata_db_model(metadata)
            metadata.save()
            metadata.dataset.save()

            orig_document = Document.objects.get_or_create(
                metadata=metadata,
                document_type=DocumentEnum.METADATA.value,
                is_original=True,
            )[0]
            orig_document.content = self.raw_metadata
            orig_document.save()

            if update:
                metadata.keywords.clear()
            for kw in self.keywords:
                keyword = Keyword.objects.get_or_create(keyword=kw)[0]
                metadata.keywords.add(keyword)
        return metadata

    def _fill_dataset_db_model(self, dataset: Dataset):
        """ Fills a Dataset db record from the ISOMetadata data

        Args:
            dataset (Dataset): The old/empty object
        Returns:
             dataset (Dataset): The dataset object
        """
        dataset.language_code = self.language
        dataset.character_set_code = self.character_set_code or "utf8"
        dataset.hierarchy_level_code = self.hierarchy_level
        dataset.update_frequency_code = self.update_frequency
        dataset.update_frequency_code = self.update_frequency
        dataset.legal_restriction_code = None
        dataset.date_stamp = self.date_stamp
        dataset.metadata_standard_name = self.md_standard_name
        dataset.metadata_standard_version = self.md_standard_version
        dataset.reference_system_code = self.ref_system
        dataset.reference_system_version = self.ref_system_version
        dataset.reference_system_authority_title = self.ref_system_authority
        dataset.md_identifier_code = self.file_identifier
        dataset.distribution_function_code = self.distribution_function or "dataset"
        dataset.lineage_statement = self.lineage
        dataset.legal_restriction_other_constraints = self.access_constraints
        dataset.use_limitation = self.use_limitation

        return dataset

    def _fill_metadata_db_model(self, metadata: Metadata):
        """ Fills a Metadata db record from the ISOMetadata data

        Args:
            metadata (Metadata): The old/empty object
        Returns:
             metadata (Metadata): The metadata object
        """
        metadata.identifier = self.file_identifier
        metadata.abstract = self.abstract
        metadata.access_constraints = self.access_constraints

        # Take the polygon with the largest area as bounding geometry
        if len(self.polygonal_extent_exterior) > 0:
            max_area_poly = None
            for poly in self.polygonal_extent_exterior:
                if max_area_poly is None:
                    max_area_poly = poly
                if max_area_poly.area < poly.area:
                    max_area_poly = poly
            metadata.bounding_geometry = max_area_poly

        try:
            metadata.contact = Organization.objects.get_or_create(
                organization_name=self.responsible_party,
                email=self.contact_email,
            )[0]
        except MultipleObjectsReturned:
            # okay, we need to create a unique organization
            # "unique" since it will only be identified using organization_name and email
            metadata.contact = Organization.objects.get_or_create(
                organization_name="{}#1".format(self.responsible_party),
                email=self.contact_email,
            )[0]

        metadata.is_inspire_conform = self.inspire_interoperability
        metadata.metadata_url = self.uri
        metadata.last_remote_change = self.last_change_date
        metadata.spatial_res_type = self.spatial_res_type
        metadata.spatial_res_value = self.spatial_res_val
        if self.title is None:
            self.title = "BROKEN"
        metadata.title = self.title
        metadata.origin = self.origin
        metadata.is_broken = self.is_broken
        metadata.save()

        # save legal dates and reports
        for report in self.legal_reports:
            report.date.save()
            report.save()
            metadata.legal_reports.add(report)
        for date in self.legal_dates:
            date.save()
            metadata.legal_dates.add(date)

        # Add links for dataset metadata
        # There is no capabilities link for dataset -> leave it None
        #447
        #metadata.capabilities_uri = None
        #metadata.service_metadata_uri = SERVICE_DATASET_URI_TEMPLATE.format(metadata.id)
        #metadata.html_metadata_uri = HTML_METADATA_URI_TEMPLATE.format(metadata.id)

        metadata.save()

        return metadata