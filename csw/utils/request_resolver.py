"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 20.05.20

"""
from django.db.models import QuerySet

from csw.utils.converter import MetadataConverter
from csw.utils.parameter import ParameterResolver
from service.helper import xml_helper
from service.models import Metadata


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


class GetRecordsResolver(RequestResolver):
    def __init__(self, param: ParameterResolver):
        super().__init__(param=param)

    def get_response(self):
        """ Creates the xml response

        Returns:
             xml_str (str): The response as string
        """
        metadata = self.get_metadata(filtered=True)
        i_from = self.param.start_position - 1
        i_to = i_from + self.param.max_records
        returned_metadata = metadata[i_from:i_to]

        md_converter = MetadataConverter(self.param, metadata, returned_metadata)
        response = md_converter.create_xml_response()

        xml_str = xml_helper.xml_to_string(response, pretty_print=True)
        return xml_str
