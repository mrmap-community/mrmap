"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 20.05.20

"""
from abc import abstractmethod
from collections import OrderedDict
from lxml.etree import Element, QName
from django.utils import timezone
from django.db.models import QuerySet

from MrMap.settings import XML_NAMESPACES, GENERIC_NAMESPACE_TEMPLATE
from csw.utils.parameter import ParameterResolver
from service.helper import xml_helper
from service.helper.enums import MetadataEnum, DocumentEnum
from service.models import Metadata, Document

GMD_SCHEMA = "http://www.isotc211.org/2005/gmd"
IDENTIFIER_TEMPLATE = "{}identifier"
TITLE_TEMPLATE = "{}title"
TYPE_TEMPLATE = "{}type"
DATE_STRF = "%Y-%m-%d"


class MetadataConverter:
    """ Creates xml representations from given metadata

    For our use case we only support the regular Dublin Core and MD_Metadata style

    """

    def __init__(self, param: ParameterResolver, all_md: QuerySet, returned_md: list):
        self.param = param
        self.all_md = all_md
        self.returned_md = returned_md

        self.ns_map = {
            "csw": "http://www.opengis.net/cat/csw/2.0.2",
            "xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "schemaLocation": "http://schemas.opengis.net/csw/2.0.2/CSW-discovery.xsd"
        }

        # Create simple access namespace prefixes
        self.csw_ns = "{" + self.ns_map["csw"] + "}"
        self.xsi_ns = "{" + self.ns_map["xsi"] + "}"

    def create_xml_response(self, with_content: bool):
        """ Creates a xml response

        Returns a response matching the requested type (GetRecords, ...)

        Args:
            with_content (bool): Whether only the outer xml should be returned or the results as well
        Returns:
             response (str): The response
        """
        request = self.param.request
        if request == "GetRecords" or request == "GetRecordById":
            return self._create_get_records_response(with_content)
        else:
            return "{} not supported".format(request)

    def _create_get_records_response(self, with_content: bool):
        """ Creates a GetRecords response

        Args:
            with_content (bool): Wether to return content or only the outer xml
        Returns:
             response (str): The response
        """
        # Create root element
        root = self._create_root_elem("GetRecordsResponse")

        # Create <csw:SearchStatus>
        search_status_element = self._create_search_status_elem()
        xml_helper.add_subelement(root, search_status_element)

        # Create <csw:SearchResults>
        search_result_element = self._create_search_results_elem(self.all_md, self.returned_md)
        xml_helper.add_subelement(root, search_result_element)

        # If the content is not requested, we can directly return the xml document in this state
        if not with_content:
            return root

        # Create metadata converter object
        if self.param.type_names == "gmd:MD_Metadata" and self.param.output_schema == GMD_SCHEMA:
            # Create Iso converter
            md_converter = Iso19115MetadataConverter(self.param, self.all_md, self.returned_md)
        else:
            # Fallback
            md_converter = DublinCoreMetadataConverter(self.param, self.all_md, self.returned_md)

        for md in self.returned_md:
            returned_metadata_element = md_converter.create_metadata_elem(md)
            xml_helper.add_subelement(search_result_element, returned_metadata_element)

        return root

    def _create_root_elem(self, operation_name: str):
        """ Creates the root element, e.g. <csw:GetRecordsResponse>

        Args:
            operation_name (str): The operation tag name (e.g. GetRecordsResponse)
        Returns:
             root (_Element): The lxml element
        """
        root = Element(
            "{}{}".format(self.csw_ns, operation_name),
            nsmap=self.ns_map,
            attrib={
                "{}schemaLocation".format(self.xsi_ns): self.ns_map.get("xsi")
            }
        )
        return root

    def _create_search_status_elem(self):
        """ Creates the <csw:SearchStatus> element

        Returns:
             search_status_elem (_Element): The lxml element
        """
        now = timezone.now()
        now = now.strftime("%Y-%m-%dT%H:%M:%S")
        search_status_elem = Element(
            "{}SearchStatus".format(self.csw_ns),
            attrib={
                "timestamp": now
            }
        )
        return search_status_elem

    def _create_search_results_elem(self, all_md: QuerySet, returned_md: list):
        """ Creates the <csw:SearchResults> element

        Returns:
             search_status_elem (_Element): The lxml element
        """
        number_of_records = all_md.count()
        number_of_records_returned = len(returned_md)
        next_record = self.param.start_position + number_of_records_returned
        next_record = next_record if next_record < number_of_records else 0

        attribs = OrderedDict()
        attribs["numberOfRecordsMatched"] = str(number_of_records)
        attribs["numberOfRecordsReturned"] = str(number_of_records_returned)
        attribs["elementSet"] = str(self.param.element_set_name or ",".join(self.param.element_name))
        attribs["nextRecord"] = str(next_record)

        elem = Element(
            "{}SearchResults".format(self.csw_ns),
            attrib=attribs
        )
        return elem

    def _create_xml_from_map(self, parent_element: Element, map: OrderedDict):
        """ Creates xml elements from a given tag-attribute map.

        Only for simple elements, which only hold a tag and text data.

        Args:
            parent_element (Element): The upper xml element
            map (OrderedDict): The tag-attribute map
        Returns:

        """
        for key, val in map.items():
            if isinstance(val, list):
                for item in val:
                    elem = xml_helper.create_subelement(
                        parent_element,
                        key
                    )
                    elem.text = item

            else:
                elem = xml_helper.create_subelement(
                    parent_element,
                    key
                )
                elem.text = val

    @abstractmethod
    def create_metadata_elem(self, returned_md: Metadata):
        pass


class Iso19115MetadataConverter(MetadataConverter):
    """ Creates a response based on the MD_Metadata from ISO19115

    """
    def __init__(self, param: ParameterResolver, all_md: QuerySet, returned_md: list):
        super().__init__(param, all_md, returned_md)

    def create_metadata_elem(self, returned_md: Metadata):
        """ Returns existing service/dataset metadata as xml elements

        Args:
            returned_md (Metadata): The processing metadata
        Returns:
             xml (Element): The xml element
        """
        if returned_md.is_dataset_metadata:
            doc = Document.objects.get(
                metadata=returned_md,
                document_type=DocumentEnum.METADATA.value,
            )
            xml = doc.content
        else:
            xml = returned_md.get_service_metadata_xml()

        xml = xml_helper.parse_xml(xml)
        xml = xml_helper.try_get_single_element_from_xml(xml_elem=xml, elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("MD_Metadata"))

        # Reduce the amount of information returned based on the requested elementSetName parameter
        xml = self.reduce_information(xml)

        return xml

    def reduce_information(self, xml: Element):
        """ Removes all elements from the xml response, which are not allowed in the requested response

        Args:
            xml (Element): The response xml
        Returns:
             xml (Element): The reduced response xml
        """
        element_set_name = self.param.element_set_name

        # The elements_to_keep are dicts, so the lookup can be much faster compared to a lookup in a list
        # Nice explaining thread can be found here:
        # https://stackoverflow.com/questions/43690191/why-are-dict-lookups-always-better-than-list-lookups
        if element_set_name == "brief":
            elements_to_keep = {
                "fileIdentifier": None,
                "hierarchyLevel": None,
                "identificationInfo": None,
            }
            xml = self._reduce_information_by_map(xml, elements_to_keep)
        elif element_set_name == "summary":
            elements_to_keep = {
                "fileIdentifier": None,
                "language": None,
                "characterSet": None,
                "hierarchyLevel": None,
                "hierarchyLevelName": None,
                "contact": None,
                "dateStamp": None,
                "metadataStandardName": None,
                "metadataStandardVersion": None,
                "referenceSystemInfo": None,
                "identificationInfo": None,
            }
            xml = self._reduce_information_by_map(xml, elements_to_keep)
        else:
            # Nothing - return like 'full' was requested
            pass

        return xml

    def _reduce_information_by_map(self, xml: Element, map: dict):
        """ Removes all elements from the xml response, which are not allowed in a brief response

        Args:
            xml (Element): The response xml
        Returns:
             xml (Element): The reduced response xml
        """
        children = xml.getchildren()
        for child in children:
            tag = QName(child).localname
            if tag not in map:
                # Remove it!
                xml_helper.remove_element(child)

        return xml


class DublinCoreMetadataConverter(MetadataConverter):

    def __init__(self, param: ParameterResolver, all_md: QuerySet, returned_md: list):
        super().__init__(param, all_md, returned_md)

        # Dublin Core namespaces
        self.dc_ns_map = {
            "dc": "http://purl.org/dc/elements/1.1/",
            "dct": "http://purl.org/dc/terms/",
            "ows": XML_NAMESPACES["ows"],
        }
        self.dc_ns = "{" + self.dc_ns_map["dc"] + "}"
        self.dct_ns = "{" + self.dc_ns_map["dct"] + "}"
        self.ows_ns = "{" + self.dc_ns_map["ows"] + "}"

    def _create_dublin_core_brief_elem(self, md: Metadata):
        """ Creates the BriefRecord in Dublin core syntax

        Args:
            md (Metadata): The metadata object providing the data
        Returns:
             elem (_Element): The lxml element
        """
        record_elem = Element(
            "{}BriefRecord".format(self.csw_ns),
            nsmap=self.dc_ns_map,
        )

        # Perform xml creation for simple elements
        attribute_element_map = OrderedDict()
        attribute_element_map[IDENTIFIER_TEMPLATE.format(self.dc_ns)] = md.identifier
        attribute_element_map[TITLE_TEMPLATE.format(self.dc_ns)] = md.title
        attribute_element_map[TYPE_TEMPLATE.format(
            self.dc_ns)] = md.metadata_type if md.metadata_type == MetadataEnum.DATASET.value else MetadataEnum.SERVICE.value

        # Create xml elements from mapped information
        self._create_xml_from_map(record_elem, attribute_element_map)

        # Perform xml creation for complex elements
        geometry = md.bounding_geometry if md.bounding_geometry is not None and md.bounding_geometry.area > 0 else md.find_max_bounding_box()
        bbox_elem = xml_helper.create_subelement(
            record_elem,
            "{}BoundingBox".format(self.ows_ns),
            attrib={
                "crs": "EPSG:{}".format(geometry.srid)
            }
        )

        bbox = geometry.extent
        lower_corner_elem = xml_helper.create_subelement(
            bbox_elem,
            "{}LowerCorner".format(self.ows_ns)
        )
        lower_corner_elem.text = "{} {}".format(bbox[0], bbox[1])
        upper_corner_elem = xml_helper.create_subelement(
            bbox_elem,
            "{}UpperCorner".format(self.ows_ns)
        )
        upper_corner_elem.text = "{} {}".format(bbox[2], bbox[3])

        return record_elem

    def _create_dublin_core_summary_elem(self, md: Metadata):
        """ Creates the SummaryRecord in Dublin core syntax

        Args:
            md (Metadata): The metadata object providing the data
        Returns:
             elem (_Element): The lxml element
        """
        record_elem = Element(
            "{}SummaryRecord".format(self.csw_ns),
            nsmap=self.dc_ns_map,
        )

        # Perform xml creation for simple elements
        attribute_element_map = OrderedDict()
        attribute_element_map[IDENTIFIER_TEMPLATE.format(self.dc_ns)] = md.identifier
        attribute_element_map[TITLE_TEMPLATE.format(self.dc_ns)] = md.title
        attribute_element_map[TYPE_TEMPLATE.format(
            self.dc_ns)] = md.metadata_type if md.metadata_type == MetadataEnum.DATASET.value else MetadataEnum.SERVICE.value
        kws = md.keywords.all()
        formats = md.get_formats()
        attribute_element_map["{}subject".format(self.dc_ns)] = [kw.keyword for kw in kws]
        attribute_element_map["{}format".format(self.dc_ns)] = [format.mime_type for format in formats]
        attribute_element_map["{}modified".format(self.dct_ns)] = md.last_modified.strftime(DATE_STRF)
        attribute_element_map["{}abstract".format(self.dct_ns)] = md.abstract

        # Create xml elements from mapped information
        self._create_xml_from_map(record_elem, attribute_element_map)

        return record_elem

    def _create_dublin_core_full_elem(self, md: Metadata):
        """ Creates the default (full) record in Dublin core syntax

        Args:
            md (Metadata): The metadata object providing the data
        Returns:
             elem (_Element): The lxml element
        """
        record_elem = Element(
            "{}Record".format(self.csw_ns),
            nsmap=self.dc_ns_map,
        )

        # Perform xml creation for simple elements
        attribute_element_map = OrderedDict()
        attribute_element_map[IDENTIFIER_TEMPLATE.format(self.dc_ns)] = md.identifier
        attribute_element_map["{}date".format(self.dc_ns)] = md.created.strftime(DATE_STRF)
        attribute_element_map[TITLE_TEMPLATE.format(self.dc_ns)] = md.title
        attribute_element_map["{}abstract".format(self.dct_ns)] = md.abstract
        attribute_element_map["{}description".format(self.dc_ns)] = md.abstract
        attribute_element_map[TYPE_TEMPLATE.format(
            self.dc_ns)] = md.metadata_type if md.metadata_type == MetadataEnum.DATASET.value else MetadataEnum.SERVICE.value
        kws = md.keywords.all()
        formats = md.get_formats()
        attribute_element_map["{}subject".format(self.dc_ns)] = [kw.keyword for kw in kws]
        attribute_element_map["{}format".format(self.dc_ns)] = [format.mime_type for format in formats]
        attribute_element_map["{}modified".format(self.dct_ns)] = md.last_modified.strftime(DATE_STRF)
        attribute_element_map["{}rights".format(self.dc_ns)] = "ToDo"  # ToDo

        # Create xml elements from mapped information
        self._create_xml_from_map(record_elem, attribute_element_map)

        # Perform xml creation for more complex elements
        # URI
        elem = xml_helper.create_subelement(
            record_elem,
            "{}URI".format(self.dc_ns),
            attrib={
                "protocol": "",
                "name": md.identifier or "",
                "description": md.abstract or "",
            }
        )
        elem.text = md.capabilities_uri

        return record_elem

    def create_metadata_elem(self, returned_md: Metadata):
        """ Creates the record in Dublin core syntax

        Args:
            md (Metadata): The metadata object providing the data
        Returns:
             elem (_Element): The lxml element
        """
        typename = self.param.element_set_name or self.param.element_name
        if typename == "brief":
            return self._create_dublin_core_brief_elem(returned_md)
        elif typename == "summary":
            return self._create_dublin_core_summary_elem(returned_md)
        else:
            return self._create_dublin_core_full_elem(returned_md)
