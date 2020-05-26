"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 20.05.20

"""
from django.db.models import QuerySet

from csw.utils.converter import MetadataConverter
from csw.utils.csw_filter import *
from csw.utils.parameter import ParameterResolver
from service.helper import xml_helper
from service.models import Metadata

SUPPORTED_VERSIONS = [
    "2.0.2",
    "3.0",
]


class RequestResolver:
    """ Resolves which type of request has to be performed.

    """

    def __init__(self, param: ParameterResolver):
        self.param = param

        self.operation_resolver_map = {
            "GetRecords": GetRecordsResolver,
            "GetRecordById": GetRecordsByIdResolver,
            "GetCapabilities": None,
            "DescribeRecord": None,
            "GetDomain": None,
            "Transaction": None,
            "Harvest": None,
        }

        self.attribute_map = {
            "dc:title": "title",
            "dc:identifier": "identifier",
            "dc:abstract": "abstract",
            "dc:description": "abstract",
            "dc:date": "created",
            "dc:modified": "last_modified",
        }

    def get_response(self):
        """ Resolve the corresponding class to perform the response fetching

        Returns:

        """
        request = self.param.request

        resolver_class = self.operation_resolver_map.get(request, None)
        if not resolver_class:
            raise ValueError(
                "No valid operation or operation not supported. Supported operations are `{}`".format(
                    ", ".join(key for key, val in self.operation_resolver_map.items() if val is not None)
                ),
                "request"
            )
        if self.param.version not in SUPPORTED_VERSIONS:
            raise ValueError(
                "{} is not supported. Choices are '{}'".format(self.param.version, ", ".join(SUPPORTED_VERSIONS)),
                "version"
            )

        class_obj = resolver_class(param=self.param)
        response = class_obj.get_response()
        return response

    def get_metadata(self, filtered: bool, sorted: bool):
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
        if sorted:
            all_md = self._sort_metadata(all_md)
        return all_md

    def _filter_metadata(self, all_md: QuerySet):
        """ Perform filtering using constraint parameter

        Args:
            all_md (QuerySet): The unfiltered metadata queryset
        Returns:
             all_md (QuerySet): The filtered metadata queryset
        """
        if self.param.constraint is None:
            return all_md
        filtered_md = filter_queryset(self.param.constraint, self.param.constraint_language, all_md)
        return filtered_md

    def _sort_metadata(self, all_md: QuerySet):
        """ Perform sorting using sortBy parameter

        Values follow the syntax of `attribute:A|D`. The A or D indicates ASC or DESC ordering. Since the
        attribute can contain `:` as well, the A|D part has to be separated without the attribute to be damaged.

        Args:
            all_md (QuerySet): The unsorted metadata queryset
        Returns:
             all_md (QuerySet): The sorted metadata queryset
        """
        if self.param.sort_by is None:
            return all_md
        sort_by_components = self.param.sort_by.split(":")
        attrib = ":".join(sort_by_components[:-1])
        md_attrib = self.attribute_map.get(attrib, None)
        if md_attrib is None:
            raise NotImplementedError(
                "{} not supported for sorting".format(attrib),
                "sortBy"
            )
        desc = sort_by_components[-1] == "D"
        if desc:
            md_attrib = "-" + md_attrib
        return all_md.order_by(md_attrib)


class GetRecordsResolver(RequestResolver):
    def __init__(self, param: ParameterResolver):
        super().__init__(param=param)

    def get_response(self):
        """ Creates the xml response

        Returns:
             xml_str (str): The response as string
        """
        metadata = self.get_metadata(
            filtered=True,
            sorted=True
        )
        i_from = self.param.start_position - 1
        i_to = i_from + self.param.max_records
        returned_metadata = metadata[i_from:i_to]
        if i_from > metadata.count():
            raise ValueError("Start position ({}) can't be greater than number of matching records ({})".format(self.param.start_position, metadata.count()), "startPosition")

        # Only return results content if this was requested
        md_converter = MetadataConverter(self.param, metadata, returned_metadata)
        response = md_converter.create_xml_response(with_content=self.param.result_type == "results")

        xml_str = xml_helper.xml_to_string(response, pretty_print=True)
        return xml_str


class GetRecordsByIdResolver(RequestResolver):
    def __init__(self, param: ParameterResolver):
        super().__init__(param=param)

    def get_response(self):
        """ Creates the xml response

        Returns:
             xml_str (str): The response as string
        """
        metadata = self.get_metadata(
            filtered=True,
            sorted=True
        ).filter(
            identifier__in=self.param.request_id.split(","),
        )
        i_from = self.param.start_position - 1
        i_to = i_from + self.param.max_records
        returned_metadata = metadata[i_from:i_to]
        if i_from > metadata.count():
            raise ValueError("Start position ({}) can't be greater than number of matching records ({})".format(self.param.start_position, metadata.count()), "startPosition")

        md_converter = MetadataConverter(self.param, metadata, returned_metadata)
        response = md_converter.create_xml_response(with_content=True)

        xml_str = xml_helper.xml_to_string(response, pretty_print=True)
        return xml_str

