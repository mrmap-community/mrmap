"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 20.05.20

"""
from collections import OrderedDict
from datetime import datetime

from django.db.models import QuerySet
from lxml.etree import Element

from MrMap.settings import XML_NAMESPACES
from csw.utils.parameter import ParameterResolver
from service.helper import xml_helper
from service.helper.enums import MetadataEnum
from service.models import Metadata

GMD_SCHEMA = "http://www.isotc211.org/2005/gmd"


class RequestResolver:
    """ Resolves which type of request has to be performed.

    """

    def __init__(self, param: ParameterResolver):
        self.param = param

        self.resolver_map = {
            "GetRecords": GetRecordsResolver,
            "GetRecordById": None,
            "GetCapabilities": None,
            "DescribeRecord": None,
            "GetDomain": None,
            "Transaction": None,
            "Harvest": None,
        }

        self.ns_map = {
            "csw": "http://www.opengis.net/cat/csw/2.0.2",
            "xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "schemaLocation": "http://schemas.opengis.net/csw/2.0.2/CSW-discovery.xsd"
        }

        # Create simple access namespace prefixes
        self.csw_ns = "{" + self.ns_map["csw"] + "}"
        self.xsi_ns = "{" + self.ns_map["xsi"] + "}"

    def get_response(self):
        """ Resolve the corresponding class to perform the response fetching

        Returns:

        """
        request = self.param.request

        resolver_class = self.resolver_map.get(request, None)
        if not resolver_class:
            raise AttributeError(
                "No valid operation or operation not supported. Choices are `{}`".format(
                    ",".join(self.resolver_map.keys())
                )
            )

        class_obj = resolver_class(param=self.param)
        response = class_obj.get_response()
        return response

    def get_metadata(self, filtered: bool):
        """ Returns available metadata

        Args:
            filtered (bool): Whether to apply given constraint filtering or not
        Returns:

        """
        all_md = Metadata.objects.filter(
            is_active=True
        )
        if filtered:
            all_md = self._filter_metadata(all_md)
        return all_md

    def _filter_metadata(self, all_md: QuerySet):
        """ Perform filtering using constraint parameter

        Args:
            all_md (QuerySet): The unfiltered metadata queryset
        Returns:
             all_md (QuerySet): The filtered metadata queryset
        """
        return all_md

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
        now = datetime.now()
        now = now.strftime("%Y-%m-%dT%H:%M:%S")
        search_status_elem = Element(
            "{}SearchStatus".format(self.csw_ns),
            attrib={
                "timestamp": now
            }
        )
        return search_status_elem

    def _create_search_results_elem(self, all_md: QuerySet, returned_md: QuerySet):
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



class GetRecordsResolver(RequestResolver):
    def __init__(self, param: ParameterResolver):
        super().__init__(param=param)

        # Dublin Core namespaces
        self.dc_ns_map = {
            "dc": "http://purl.org/dc/elements/1.1/",
            "dct": "http://purl.org/dc/terms/",
            "ows": XML_NAMESPACES["ows"],
        }
        self.dc_ns = "{" + self.dc_ns_map["dc"] + "}"
        self.dct_ns = "{" + self.dc_ns_map["dct"] + "}"

    def _create_dublin_core_brief_elem(self, md: Metadata):
        """ Creates the BriefRecord in Dublin core syntax

        Args:
            md (Metadata): The metadata object providing the data
        Returns:
             elem (_Element): The lxml element
        """
        pass

    def _create_dublin_core_summary_elem(self, md: Metadata):
        """ Creates the SummaryRecord in Dublin core syntax

        Args:
            md (Metadata): The metadata object providing the data
        Returns:
             elem (_Element): The lxml element
        """
        pass

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

        # Identifier
        elem = xml_helper.create_subelement(
            record_elem,
            "{}identifier".format(self.dc_ns),
        )
        elem.text = md.identifier

        # Date
        elem = xml_helper.create_subelement(
            record_elem,
            "{}date".format(self.dc_ns),
        )
        elem.text = md.created.strftime("%Y-%m-%d")

        # Title
        elem = xml_helper.create_subelement(
            record_elem,
            "{}title".format(self.dc_ns),
        )
        elem.text = md.title

        # Abstract
        elem = xml_helper.create_subelement(
            record_elem,
            "{}abstract".format(self.dct_ns),
        )
        elem.text = md.abstract

        # Description
        elem = xml_helper.create_subelement(
            record_elem,
            "{}abstract".format(self.dc_ns),
        )
        elem.text = md.abstract

        # Type
        elem = xml_helper.create_subelement(
            record_elem,
            "{}type".format(self.dc_ns),
        )
        elem.text = md.metadata_type.type if md.metadata_type.type == MetadataEnum.DATASET.value else "service"

        # Subjects
        for kw in md.keywords.all():
            elem = xml_helper.create_subelement(
                record_elem,
                "{}subject".format(self.dc_ns),
            )
            elem.text = kw.keyword

        # Formats
        for _format in md.formats.all():
            elem = xml_helper.create_subelement(
                record_elem,
                "{}format".format(self.dc_ns),
            )
            elem.text = _format.mime_type

        # Modified
        elem = xml_helper.create_subelement(
            record_elem,
            "{}modified".format(self.dct_ns),
        )
        elem.text = md.last_modified.strftime("%Y-%m-%d")

        # Rights
        elem = xml_helper.create_subelement(
            record_elem,
            "{}rights".format(self.dc_ns),
        )
        elem.text = "ToDo"

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

    def _create_dublin_core_elems(self, returned_md: Metadata):
        """ Creates the record in Dublin core syntax

        Args:
            md (Metadata): The metadata object providing the data
        Returns:
             elem (_Element): The lxml element
        """
        typename = self.param.type_names
        if typename == "brief":
            return self._create_dublin_core_brief_elem(returned_md)
        elif typename == "summary":
            return self._create_dublin_core_summary_elem(returned_md)
        else:
            return self._create_dublin_core_full_elem(returned_md)

    def _create_returned_metadata_elem(self, returned_md: Metadata):
        ret_elements = None
        if self.param.type_names == "gmd:MD_Metadata" and self.param.output_schema == GMD_SCHEMA:
            # ToDo: ISO19115
            ret_elements = ""
        else:
            # ToDo: Dublin core as fallback
            ret_elements = self._create_dublin_core_elems(returned_md)
        return ret_elements

    def get_response(self):
        """ Creates the xml response

        Returns:
             xml_str (str): The response as string
        """
        metadata = self.get_metadata(filtered=True)
        i_from = self.param.start_position - 1
        i_to = i_from + self.param.max_records
        returned_metadata = metadata[i_from:i_to]

        # Create root element
        root = self._create_root_elem("GetRecordsResponse")

        # Create <csw:SearchStatus>
        search_status_element = self._create_search_status_elem()
        xml_helper.add_subelement(root, search_status_element)

        # Create <csw:SearchResults>
        search_result_element = self._create_search_results_elem(metadata, returned_metadata)
        xml_helper.add_subelement(root, search_result_element)

        for md in returned_metadata:
            returned_metadata_element = self._create_returned_metadata_elem(md)
            xml_helper.add_subelement(search_result_element, returned_metadata_element)

        xml_str = xml_helper.xml_to_string(root, pretty_print=True)
        return xml_str
