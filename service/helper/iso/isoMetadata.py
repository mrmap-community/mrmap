"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 04.07.2019

"""
import json

from django.contrib.gis.geos import Polygon
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from MapSkinner.settings import XML_NAMESPACES
from MapSkinner import utils
from service.config import INSPIRE_LEGISLATION_FILE
from service.helper import service_helper
from service.helper.common_connector import CommonConnector
from service.helper.enums import ConnectionType
from service.helper.epsg_api import EpsgApi
from service.models import Metadata, Keyword
from structure.models import Organization


class ISOMetadata:
    def __init__(self, uri: str, origin: str = "capabilities"):
        self.section = "all" # serviceIdentification, serviceProvider, operationMetadata, contents, all

        self.uri = uri
        self.raw_metadata = None

        # referenced from mapbender metadata parsing
        self.file_identifier = None
        self.create_date = None
        self.last_change_date = None
        self.hierarchy_level = None
        self.title = None
        self.abstract = None
        self.keywords = []
        self.iso_categories = []
        self.download_link = None
        self.transfer_size = None
        self.preview_image = None
        self.bounding_box = {
            "min_x": None,
            "min_y": None,
            "max_x": None,
            "max_y": None,
        }
        # ToDo: datasetId / datasetIdCode missing

        self.polygonal_extent_exterior = []
        self.tmp_extent_begin = None
        self.tmp_extent_end = None

        self.spatial_res_val = None
        self.spatial_res_type = None
        self.ground_resolution = None
        self.ref_system = None
        self.lineage = None

        self.license_source_note = None
        self.license_json = None
        self.fees = None

        self.access_constraints = None
        self.responsible_party = None
        self.contact_email = None
        self.update_frequency = None
        self.valid_update_frequencies = ['continual', 'daily', 'weekly', 'fortnightly', 'monthly', 'quarterly', 'biannually', 'annually', 'asNeeded', 'irregular', 'notPlanned', 'unknown']

        self.inspire_interoperability = True
        self.interoperability_list = []
        self.origin = origin

        XML_NAMESPACES["gmd"] = "http://www.isotc211.org/2005/gmd"
        XML_NAMESPACES["gco"] = "http://www.isotc211.org/2005/gco"
        XML_NAMESPACES["gml"] = "http://www.opengis.net/gml"
        XML_NAMESPACES["srv"] = "http://www.isotc211.org/2005/srv"
        XML_NAMESPACES["xlink"] = "http://www.w3.org/1999/xlink"
        XML_NAMESPACES["xsi"] = "http://www.w3.org/2001/XMLSchema-instance"
        XML_NAMESPACES["inspire_common"] = "http://inspire.ec.europa.eu/schemas/common/1.0"
        XML_NAMESPACES["inspire_vs"] = "http://inspire.ec.europa.eu/schemas/inspire_vs/1.0"
        # XML_NAMESPACES["default"] = ""

        # load uri and start parsing
        self.get_metadata()
        self.parse_xml()

    def get_metadata(self):
        """ Start a network call to retrieve the original capabilities xml document.

        Using the connector class, this function will GET the capabilities xml document as string.
        No file will be downloaded and stored on the storage. The string will be stored in the OGCWebService instance.

        Returns:
             nothing
        """
        ows_connector = CommonConnector(url=self.uri,
                                        auth=None,
                                        connection_type=ConnectionType.REQUESTS)
        ows_connector.http_method = 'GET'
        ows_connector.load()
        if ows_connector.status_code != 200:
            raise ConnectionError(ows_connector.status_code)
        if ows_connector.encoding is not None:
            self.raw_metadata = ows_connector.content.decode(ows_connector.encoding)
        else:
            self.raw_metadata = ows_connector.text

    def parse_xml(self):
        """ Reads the needed data from the xml into the ISOMetadata

        Returns:
             nothing
        """
        xml = self.raw_metadata
        xml_obj = service_helper.parse_xml(xml)
        self.file_identifier = service_helper.try_get_text_from_xml_element(xml_obj, "//gmd:MD_Metadata/gmd:fileIdentifier/gco:CharacterString")
        self.create_date = service_helper.try_get_text_from_xml_element(xml_obj, "//gmd:MD_Metadata/gmd:dateStamp/gco:Date")
        self.last_change_date = service_helper.try_get_text_from_xml_element(xml_obj, "//gmd:MD_Metadata/gmd:dateStamp/gco:Date")
        self.hierarchy_level = service_helper.try_get_text_from_xml_element(xml_obj, "//gmd:MD_Metadata/gmd:hierarchyLevel/gmd:MD_ScopeCode")
        if self.hierarchy_level == "service":
            xpath_type = "srv:SV_ServiceIdentification"
        else:
            xpath_type = "gmd:MD_DataIdentification"
        self.title = service_helper.try_get_text_from_xml_element(xml_obj, "//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:citation/gmd:CI_Citation/gmd:title/gco:CharacterString".format(xpath_type))
        self.abstract = service_helper.try_get_text_from_xml_element(xml_obj, "//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:abstract/gco:CharacterString".format(xpath_type))

        keywords = service_helper.try_get_element_from_xml(xml_elem=xml_obj, elem="//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:descriptiveKeywords/gmd:MD_Keywords/gmd:keyword/gco:CharacterString".format(xpath_type))
        for keyword in keywords:
            self.keywords.append(service_helper.try_get_text_from_xml_element(keyword))

        iso_categories = service_helper.try_get_element_from_xml(xml_elem=xml_obj, elem="//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:topicCategory/gmd:MD_TopicCategoryCode".format(xpath_type))
        for iso_category in iso_categories:
            self.iso_categories.append(service_helper.try_get_text_from_xml_element(iso_category))

        self.download_link = service_helper.try_get_text_from_xml_element(xml_obj, '//gmd:MD_Metadata/gmd:distributionInfo/gmd:MD_Distribution/gmd:transferOptions/gmd:MD_DigitalTransferOptions/gmd:onLine/gmd:CI_OnlineResource[gmd:function/gmd:CI_OnLineFunctionCode/@codeListValue="download"]/gmd:linkage/gmd:URL')
        self.transfer_size = service_helper.try_get_text_from_xml_element(xml_obj, '//gmd:MD_Metadata/gmd:distributionInfo/gmd:MD_Distribution/gmd:transferOptions/gmd:MD_DigitalTransferOptions/gmd:transferSize/gco:Real')
        self.preview_image = service_helper.try_get_text_from_xml_element(xml_obj, "//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:graphicOverview/gmd:MD_BrowseGraphic/gmd:fileName/gco:CharacterString".format(xpath_type))
        self.bounding_box["min_x"] = service_helper.try_get_text_from_xml_element(xml_obj, "//gmd:westBoundLongitude/gco:Decimal".format(xpath_type))
        self.bounding_box["min_y"] = service_helper.try_get_text_from_xml_element(xml_obj, "//gmd:southBoundLatitude/gco:Decimal".format(xpath_type))
        self.bounding_box["max_x"] = service_helper.try_get_text_from_xml_element(xml_obj, "//gmd:eastBoundLongitude/gco:Decimal".format(xpath_type))
        self.bounding_box["max_y"] = service_helper.try_get_text_from_xml_element(xml_obj, "//gmd:northBoundLatitude/gco:Decimal".format(xpath_type))

        polygons = service_helper.try_get_element_from_xml(xml_elem=xml_obj, elem='//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:extent/gmd:EX_Extent/gmd:geographicElement/gmd:EX_BoundingPolygon/gmd:polygon/gml:MultiSurface'.format(xpath_type))
        if len(polygons) > 0:
            surface_elements = service_helper.try_get_element_from_xml(xml_elem=xml_obj, elem="//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:extent/gmd:EX_Extent/gmd:geographicElement/gmd:EX_BoundingPolygon/gmd:polygon/gml:MultiSurface/gml:surfaceMember".format(xpath_type))
            i = 0
            for element in surface_elements:
                self.polygonal_extent_exterior.append(self.parse_polygon(element))
                i += 1
        else:
            polygons = service_helper.try_get_text_from_xml_element(xml_obj, '//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:extent/gmd:EX_Extent/gmd:geographicElement/gmd:EX_BoundingPolygon/gmd:polygon/gml:Polygon'.format(xpath_type))
            if polygons is not None:
                self.polygonal_extent_exterior.append(service_helper.try_get_text_from_xml_element(xml_obj, "//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:extent/gmd:EX_Extent/gmd:geographicElement/gmd:EX_BoundingPolygon/gmd:polygon".format(xpath_type)))

        self.tmp_extent_begin = service_helper.try_get_text_from_xml_element(xml_obj, "//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:extent/gmd:EX_Extent/gmd:temporalElement/gmd:EX_TemporalExtent/gmd:extent/gml:TimePeriod/gml:beginPosition".format(xpath_type))
        if self.tmp_extent_begin is None:
            self.tmp_extent_begin = "1900-01-01"

        self.tmp_extent_end = service_helper.try_get_text_from_xml_element(xml_obj, "//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:extent/gmd:EX_Extent/gmd:temporalElement/gmd:EX_TemporalExtent/gmd:extent/gml:TimePeriod/gml:endPosition".format(xpath_type))
        if self.tmp_extent_end is None:
            self.tmp_extent_end = "1900-01-01"

        equivalent_scale = service_helper.try_get_text_from_xml_element(xml_obj, "//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:spatialResolution/gmd:MD_Resolution/gmd:equivalentScale/gmd:MD_RepresentativeFraction/gmd:denominator/gco:Integer".format(xpath_type))
        ground_res = service_helper.try_get_text_from_xml_element(xml_obj, "//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:spatialResolution/gmd:MD_Resolution/gmd:distance/gco:Distance".format(xpath_type))
        if equivalent_scale is not None and int(equivalent_scale) > 0:
            self.spatial_res_val = equivalent_scale
            self.spatial_res_type = "scaleDenominator"
        elif ground_res is not None and len(ground_res) > 0:
            self.spatial_res_val = ground_res
            self.spatial_res_type = "groundDistance"

        self.ref_system = service_helper.try_get_text_from_xml_element(xml_obj, "//gmd:MD_Metadata/gmd:referenceSystemInfo/gmd:MD_ReferenceSystem/gmd:referenceSystemIdentifier/gmd:RS_Identifier/gmd:code/gco:CharacterString")
        epsg_api = EpsgApi()
        if self.ref_system is not None:
            self.ref_system = "EPSG:{}".format(epsg_api.get_subelements(self.ref_system).get("code"))

        self.lineage = service_helper.try_get_text_from_xml_element(xml_obj, "//gmd:MD_Metadata/gmd:dataQualityInfo/gmd:DQ_DataQuality/gmd:lineage/gmd:LI_Lineage/gmd:statement/gco:CharacterString")

        restriction_code_attr_val = service_helper.try_get_element_from_xml(xml_elem=xml_obj, elem='//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:resourceConstraints/gmd:MD_LegalConstraints/gmd:useConstraints/gmd:MD_RestrictionCode/@codeListValue'.format(xpath_type))
        if len(restriction_code_attr_val) >= 2:
            legal_constraints = ""
            if restriction_code_attr_val[0] == 'license' and restriction_code_attr_val[1] == 'otherRestrictions':
                other_constraints = service_helper.try_get_element_from_xml(xml_elem=xml_obj, elem='//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:resourceConstraints/gmd:MD_LegalConstraints[gmd:useConstraints/gmd:MD_RestrictionCode/@codeListValue="otherRestrictions"]/gmd:otherConstraints/gco:CharacterString'.format(xpath_type))
                for constraint in other_constraints:
                    try:
                        tmp_constraint = service_helper.try_get_text_from_xml_element(xml_elem=constraint)
                        constraint_json = json.loads(tmp_constraint)
                        self.license_source_note = constraint_json.get("quelle", None)
                        self.license_json = constraint_json
                    except ValueError:
                        # no, this is not a json!
                        # handle it is a normal text
                        legal_constraints += tmp_constraint + ";"
            self.fees = legal_constraints

        self.access_constraints = service_helper.try_get_text_from_xml_element(xml_obj, '//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:resourceConstraints/gmd:MD_LegalConstraints[gmd:accessConstraints/gmd:MD_RestrictionCode/@codeListValue="otherRestrictions"]/gmd:otherConstraints/gco:CharacterString'.format(xpath_type))
        self.responsible_party = service_helper.try_get_text_from_xml_element(xml_obj, '//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:pointOfContact/gmd:CI_ResponsibleParty/gmd:organisationName/gco:CharacterString'.format(xpath_type))
        self.contact_email = service_helper.try_get_text_from_xml_element(xml_obj, '//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:pointOfContact/gmd:CI_ResponsibleParty/gmd:contactInfo/gmd:CI_Contact/gmd:address/gmd:CI_Address/gmd:electronicMailAddress/gco:CharacterString'.format(xpath_type))
        update_frequency = service_helper.try_get_attribute_from_xml_element(xml_elem=xml_obj, attribute="codeListValue", elem='//gmd:MD_Metadata/gmd:identificationInfo/{}/gmd:resourceMaintenance/gmd:MD_MaintenanceInformation/gmd:maintenanceAndUpdateFrequency/gmd:MD_MaintenanceFrequencyCode'.format(xpath_type))
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
            statement = service_helper.try_get_text_from_xml_element(xml_obj, '//gmd:MD_Metadata/gmd:dataQualityInfo/gmd:DQ_DataQuality/gmd:report/gmd:DQ_DomainConsistency/gmd:result/gmd:DQ_ConformanceResult[gmd:specification/gmd:CI_Citation/gmd:title/gco:CharacterString="{}" and gmd:specification/gmd:CI_Citation/gmd:date/gmd:CI_Date/gmd:date/gco:Date="{}"]/gmd:pass/gco:Boolean'.format(reg["name"], reg["date"]))
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

    def parse_polygon(self, polygon_elem):
        """ Creates points from continuous polygon points array

        Args:
            polygon: The etree xml element which holds the polygons
        Returns:
             polygon (Polygon): The polygon object created from the data
        """
        polygon = Polygon()
        relative_ring_xpath = "./gml:Polygon/gml:exterior/gml:LinearRing/gml:posList"
        relative_coordinate_xpath = "./gml:Polygon/gml:exterior/gml:LinearRing/gml:coordinates"
        pos_list = service_helper.try_get_element_from_xml(xml_elem=polygon_elem, elem=relative_ring_xpath)
        min_x = 10000
        max_x = 0
        min_y = 100000
        max_y = 0
        if len(pos_list) > 0:
            exterior_ring_points = service_helper.try_get_text_from_xml_element(xml_elem=polygon_elem, elem=relative_ring_xpath)
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
            exterior_ring_points = service_helper.try_get_text_from_xml_element(xml_elem=polygon_elem, elem=relative_coordinate_xpath)
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
    def get_db_model(self):
        """ Get corresponding metadata object from database or create it if not found!

        Returns:
            metadata (Metadata): A db model Metadata object
        """
        # try to find the object by uuid and uri
        update = False
        new = False
        try:
            metadata = Metadata.objects.get(uuid=self.file_identifier, original_uri=self.uri)
            # check if the parsed metadata might be newer
            if metadata.last_modified != self.last_change_date:
                update = True
        except ObjectDoesNotExist:
            # object does not seem to exist -> create it!
            metadata = Metadata()
            new = True
        if update or new:
            metadata.uuid = self.file_identifier
            metadata.abstract = self.abstract
            metadata.access_constraints = self.access_constraints
            # metadata.bbox = self.bounding_box
            if len(self.polygonal_extent_exterior) > 0:
                metadata.bounding_geometry = self.polygonal_extent_exterior[0]
            # hopefully find the contact using the email!
            metadata.contact = Organization.objects.get_or_create(
                organization_name=self.responsible_party
            )[0]
            metadata.is_inspire_conform = self.inspire_interoperability
            metadata.metadata_url = self.uri
            metadata.last_modified = self.last_change_date
            metadata.spatial_res_type = self.spatial_res_type
            metadata.spatial_res_value = self.spatial_res_val
            metadata.title = self.title
            metadata.origin = self.origin
            metadata.save()
            if update:
                metadata.keywords.clean()
            for kw in self.keywords:
                keyword = Keyword.objects.get_or_create(keyword=kw)[0]
                metadata.keywords.add(keyword)
        return metadata