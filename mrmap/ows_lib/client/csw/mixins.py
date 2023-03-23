import re

from ows_lib.client.mixins import OgcClient
from ows_lib.client.utils import update_queryparams
from requests import Request


class CatalogueServiceMixin(OgcClient):

    def queryable_type_name(self):
        """Returns the first matching string of the constraints list which matches the name 'type'"""
        prog = re.compile(r'(\w+:type$)|(^type$)')
        if any((match := prog.match(item)) for item in self.capabilities.get_records_constraints):
            return match.group(0)
        else:
            return type

    def get_constraint(self, record_type):
        type_name = self.queryable_type_name()
        return f'<ogc:Filter xmlns:ogc="http://www.opengis.net/ogc"><ogc:PropertyIsEqualTo><ogc:PropertyName>{type_name}</ogc:PropertyName><ogc:Literal>{record_type}</ogc:Literal></ogc:PropertyIsEqualTo></ogc:Filter>'

    def prepare_get_records_request(
        self,
        type_names: str = "gmd:MD_Metadata",
        result_type: str = "hits",
        output_schema: str = "http://www.isotc211.org/2005/gmd",
        element_set_name: str = "full",
        xml_constraint: str = None,
        max_records: int = None,
        start_position: int = None,

    ) -> Request:

        params = {
            "VERSION": self.capabilities.service_type.version,
            "REQUEST": "GetRecords",
            "SERVICE": "CSW",
            "typeNames": type_names,
            "resultType": result_type,
            "outputSchema": output_schema,
            "elementSetName": element_set_name,
        }

        if xml_constraint:
            params.update({
                "constraintLanguage": "FILTER",
                "CONSTRAINT_LANGUAGE_VERSION": "1.1.0",
                "Constraint": xml_constraint
            })

        if max_records:
            params.update({
                "maxRecords": max_records
            })

        if start_position:
            params.update({
                "startPosition": start_position
            })

        url = update_queryparams(
            url=self.capabilities.get_operation_url_by_name_and_method(
                "GetRecords", "Get").url,
            params=params)

        return Request(method="GET", url=url)

    def prepare_get_record_by_id_request(
        self,
        id: str,
        output_schema: str = "http://www.isotc211.org/2005/gmd",
        element_set_name: str = "full",
    ) -> Request:
        params = {
            "VERSION": self.capabilities.service_type.version,
            "SERVICE": "CSW",
            "REQUEST": "GetRecordById",
            "outputSchema": output_schema,
            "elementSetName": element_set_name,
            "id": id,
        }

        url = update_queryparams(
            url=self.capabilities.get_operation_url_by_name_and_method(
                "GetRecordById", "Get").url,
            params=params)

        return Request(method="GET", url=url)
