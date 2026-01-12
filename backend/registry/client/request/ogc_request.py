from typing import Dict, List

from django.contrib.gis.geos import GEOSGeometry
from django.db.models.query_utils import Q
from django.http.request import HttpRequest as DjangoRequest
from eulxml.xmlmap import XmlObject, load_xmlobject_from_string
from lark.exceptions import LarkError
from lxml.etree import XMLSyntaxError, etree
from pygeofilter.backends.django.evaluate import to_filter
from pygeofilter.parsers.ecql import parse as parse_ecql
from pygeofilter.parsers.fes.util import NodeParsingError
from registry.client.contrib.fes.parser import parse as parse_fes
from registry.client.exceptions import (InvalidParameterValueException,
                                        MissingBboxParam,
                                        MissingConstraintLanguageParameter,
                                        MissingServiceParam)
from registry.client.utils import (construct_polygon_from_bbox_query_param,
                                   get_requested_feature_types,
                                   get_requested_layers, get_requested_records)
from registry.enums.service import OGCOperationEnum
from requests import Request


class OGCRequest(Request):
    """Extended Request class which provides some analyzing functionality for ogc requests."""

    def __init__(self, django_request: DjangoRequest = None, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._djano_request = django_request
        self._ogc_query_params: Dict = {}
        self._bbox: GEOSGeometry = None
        self._requested_entities: List[str] = []
        self._xml_request: XmlObject = None
        self.operation = "unknown"
        self.service_version = "unknown"
        self.service_type = "unknown"

        if self.method == "GET":
            self.operation: str = self.ogc_query_params.get("REQUEST", "")
            self.service_version: str = self.ogc_query_params.get(
                "VERSION", "")
            self.service_type: str = self.ogc_query_params.get("SERVICE", "")
        elif self.method == "POST" and self.data and isinstance(self.data, bytes):
            post_request = etree.fromstring(self.data)
            nsmap = post_request.nsmap.copy()
            self.operation = post_request.xpath(
                "local-name()",
                namespaces=nsmap,
            )
            self.service_version = post_request.get("@version")
            self.service_type = post_request.get("@service")

    @classmethod
    def from_django_request(cls, request: DjangoRequest):
        """helper function to construct an OGCRequest from a django request object."""
        ogc_request = cls(
            method=request.method,
            url=request.build_absolute_uri(),
            params={**request.GET, **request.POST},
            data=request.body,
            cookies=request.COOKIES,
            django_request=request
        )
        return ogc_request

    @property
    def requested_entities(self) -> List[str]:
        """Returns the list of requested entities

        This function analyzes the request and find out which layers or featuretypes, or records are requested.

        :return: list of requested layers | list of request featuretypes
        :rtype: List[str]
        """
        if not self._requested_entities:
            if self.is_wms:
                self._requested_entities.extend(
                    get_requested_layers(params=self.ogc_query_params))
            elif self.is_get_feature_request:
                if self.is_get:
                    self._requested_entities.extend(
                        get_requested_feature_types(params=self.ogc_query_params))
                elif self.is_post:
                    self._requested_entities.extend(
                        self.xml_request.requested_feature_types)
            elif self.is_get_record_by_id_request:
                if self.is_get:
                    self._requested_entities.extend(
                        get_requested_records(params=self.ogc_query_params)
                    )
                elif self.is_post:
                    self._requested_entities.extend(
                        self.xml_request.ids)
            else:
                pass
        return self._requested_entities

    def filter_constraint(self, field_mapping=None, mapping_choices=None) -> Q:
        if self.is_csw and self.is_get_records_request:
            if self.is_get:
                constraint = self.ogc_query_params.get("Constraint", "")
                constraint_language = self.ogc_query_params.get(
                    "CONSTRAINTLANGUAGE", "")
                if constraint and not constraint_language:
                    return MissingConstraintLanguageParameter(ogc_request=self)

                elif constraint and constraint_language:
                    if constraint_language == "CQL_TEXT":
                        try:
                            ast = parse_ecql(constraint)
                            return to_filter(ast, field_mapping, mapping_choices)
                        except LarkError as e:
                            return InvalidParameterValueException(ogc_request=self, message=e)
                    elif constraint_language == "FILTER":
                        try:
                            ast = parse_fes(constraint)
                            return to_filter(ast, field_mapping, mapping_choices)
                        except (XMLSyntaxError, NodeParsingError) as e:
                            return InvalidParameterValueException(
                                ogc_request=self,
                                message=e
                            )
                    else:
                        return InvalidParameterValueException(
                            ogc_request=self,
                            message="Provided CONSTRAINTLANGUAGE is not supported.")
            elif self.is_post:
                return self.xml_request.get_django_filter(field_mapping, mapping_choices)

        return Q()

    @property
    def is_wms(self) -> bool:
        """Check for wms request

        :return: true if this is a wms request
        :rtype: bool
        """
        return self.service_type.lower() == 'wms'

    @property
    def is_wfs(self) -> bool:
        """Check for wfs request

        :return: true if this is a wfs request
        :rtype: bool
        """
        return self.service_type.lower() == 'wfs'

    @property
    def is_csw(self) -> bool:
        """Check for wfs request

        :return: true if this is a wfs request
        :rtype: bool
        """
        return self.service_type.lower() == 'csw'

    @property
    def is_post(self) -> bool:
        """Check for post method

        :return: true if this is a post request
        :rtype: bool
        """
        return self.method.lower() == "post"

    @property
    def is_get(self) -> bool:
        """Check for get method

        :return: true if this is a post request
        :rtype: bool
        """
        return self.method.lower() == "get"

    @property
    def is_get_capabilities_request(self) -> bool:
        """Check for ogc get capabilites request

        :return: true if this is a get capabilities request
        :rtype: bool
        """
        return self.operation == OGCOperationEnum.GET_CAPABILITIES.label

    @property
    def is_get_map_request(self) -> bool:
        """Check for wms get map request

        :return: true if this is a wms get map request
        :rtype: bool
        """
        return self.operation == OGCOperationEnum.GET_MAP.label

    @property
    def is_get_feature_info_request(self) -> bool:
        """Check for wms transaction request

        :return: true if this is a wfs tranasction request
        :rtype: bool
        """
        return self.operation == OGCOperationEnum.GET_FEATURE_INFO.label

    @property
    def is_get_feature_request(self) -> bool:
        """Check for wfs get feature request

        :return: true if this is a wfs get feature request
        :rtype: bool
        """
        return self.operation == OGCOperationEnum.GET_FEATURE.label

    @property
    def is_transaction_request(self) -> bool:
        """Check for wfs transaction request

        :return: true if this is a wfs tranasction request
        :rtype: bool
        """
        return self.operation == OGCOperationEnum.TRANSACTION.label

    @property
    def is_describe_record_request(self) -> bool:
        return self.operation == OGCOperationEnum.DESCRIBE_RECORD.label

    @property
    def is_get_record_by_id_request(self) -> bool:
        return self.operation == OGCOperationEnum.GET_RECORD_BY_ID.label

    @property
    def is_get_records_request(self) -> bool:
        return self.operation == OGCOperationEnum.GET_RECORDS.label

    @property
    def bbox(self) -> GEOSGeometry:
        """Analyzes the given request and tries to construct a Polygon from the query parameters.

        The axis order for different wms/wfs versions will be well transformed to the correct needed mathematical interpretation.

        :raises MissingBboxParam: if the bbox query param is missing
        :raises MissingServiceParam: if the service query param is missing. Without that the correct axis order can't be interpreted.

        :return: the given bbox as polygon object
        :rtype: GEOSGeometry
        """
        if not self._bbox:
            try:
                self._bbox = construct_polygon_from_bbox_query_param(
                    get_dict=self.ogc_query_params)
            except (MissingBboxParam, MissingServiceParam):
                # only to avoid error while handling sql in service property
                self._bbox = GEOSGeometry("POLYGON EMPTY")
        return self._bbox

    @property
    def ogc_query_params(self) -> Dict:
        """ Parses the GET parameters into all member variables, which can be found in a ogc request.

        :return: all ogc query parameters
        :rtype: Dict
        """
        if not self._ogc_query_params:
            query_keys = ["SERVICE", "REQUEST", "LAYERS", "BBOX", "VERSION", "FORMAT",
                          "OUTPUTFORMAT", "SRS", "CRS", "SRSNAME", "WIDTH", "HEIGHT",
                          "TRANSPARENT", "EXCEPTIONS", "BGCOLOR", "TIME", "ELEVATION",
                          "QUERY_LAYERS", "INFO_FORMAT", "FEATURE_COUNT", "I", "J",
                          "NAMESPACE", "resultType", "requestId", "TypeName", "outputFormat",
                          "outputSchema", "startPosition", "maxRecords", "schemaLanguage",
                          "ElementSetName", "ElementName", "typeNames", "CONSTRAINTLANGUAGE",
                          "Constraint", "SortBy", "DistributedSearch",
                          "hopCount", "ResponseHandler", "Id"]

            for key in query_keys:
                value = self.params.get(key, self.params.get(key.lower(), ""))

                if value:
                    if isinstance(value, list):
                        # if multiple values are passed in multiple queryparams, we pick the first item
                        value = value[0]

                    self._ogc_query_params.update({
                        key: value
                    })

        return self._ogc_query_params

    @property
    def xml_request(self) -> XmlObject:
        """Constructs a xml request object based on the given request.

        This function analyzes the given request by its method and operation. 
        If it is a get request, the get feature operation for example will be converted to an postable xml object.

        :return: The mapped xml object
        :rtype: XmlObject
        """
        if not self._xml_request:
            # TODO: implement the xml request generation for other requests too.
            if self.is_get_feature_request:  # NOSONAR: See todo above
                # FIXME: depending on version, different xml mapper are needed...
                if self.is_post:
                    self._xml_request = etree.fromstring(self.data)
                elif self.is_get:
                    # we construct a xml get feature request to post it with a filter
                    queries: List[Query] = []
                    for feature_type in self.requested_entities:
                        query: Query = Query()
                        query.type_names = feature_type
                        queries.append(query)
                    self._xml_request: GetFeatureRequest = GetFeatureRequest()
                    self._xml_request.queries = queries
            elif self.is_get_records_request:
                if self.is_post:
                    self._xml_request: GetRecordsRequest = load_xmlobject_from_string(
                        string=self.data, xmlclass=GetRecordsRequest)
                elif self.is_get:
                    sort_by = self.ogc_query_params.get("SortBy")
                    if sort_by:
                        element_name, a_or_d = sort_by.split(":")
                        if a_or_d == "A":
                            sort_by = element_name
                        elif a_or_d == "D":
                            sort_by = f"-{element_name}"
                    constraint = self.ogc_query_params.get("Constraint")
                    constraint_language = self.ogc_query_params.get(
                        "CONSTRAINTLANGUAGE")
                    self._xml_request = GetRecordsRequest()
                    self._xml_request.service_version = self.ogc_query_params.get(
                        "VERSION")
                    self._xml_request.service_type = self.ogc_query_params.get(
                        "SERVICE")
                    self._xml_request.result_type = self.ogc_query_params.get(
                        "resultType")
                    self._xml_request.start_position = self.ogc_query_params.get(
                        "startPosition")
                    self._xml_request.max_records = self.ogc_query_params.get(
                        "maxRecords")
                    self._xml_request.element_set_name = self.ogc_query_params.get(
                        "ElementSetName")
                    self._xml_request.sort_by = sort_by
                    if constraint and constraint_language == "CQL_TEXT":
                        self._xml_request.cql_filter = constraint
                        self._xml_request.constraint_version = "1.1.0"
                    elif constraint and constraint_language == "FILTER":
                        self._xml_request.fes_filter = load_xmlobject_from_string(
                            constraint, XmlObject)
                        self._xml_request.constraint_version = "1.1.0"
            elif self.is_get_record_by_id_request:
                if self.is_post:
                    self._xml_request: GetRecordByIdRequest = load_xmlobject_from_string(
                        string=self.data, xmlclass=GetRecordByIdRequest)
                elif self.is_get:
                    self._xml_request = GetRecordByIdRequest()
                    self._xml_request.service_version = self.ogc_query_params.get(
                        "VERSION")
                    self._xml_request.service_type = self.ogc_query_params.get(
                        "SERVICE")
                    self._xml_request.element_set_name = self.ogc_query_params.get(
                        "ElementSetName")
                    self._xml_request.ids = self.ogc_query_params.get(
                        "id", "").split(",")
        return self._xml_request
