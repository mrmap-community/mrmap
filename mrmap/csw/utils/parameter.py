"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 20.05.20

"""
from django.http import HttpRequest

from csw.utils.csw_filter import CONSTRAINT_LOCATOR

INVALID_PARAMETER_TEMPLATE = "Parameter '{}' invalid! Choices are '{}'"

RESULT_TYPE_CHOICES = {
    "hits": None,
    "results": None,
    "validate": None,
}

ELEMENT_SET_CHOICES = {
    "full": None,
    "summary": None,
    "brief": None,
}

VERSION_CHOICES = {
    "2.0.2": None,
    # "3.0": None,  # not supported yet
}

class ParameterResolver:
    """ Wraps all possible parameters for an incoming GetRecords request

    This follows the specification of a OGC CSW, which can be found here:
    https://www.ogc.org/standards/cat

    """
    def __init__(self, param_dict: dict):
        self.request = None                 # mandatory, multiplicity: 1
        self.service = None                 # mandatory, multiplicity: 1
        self.version = None                 # mandatory, multiplicity: 1
        self.namespace = []                 # optional, multiplicity: 0|1, comma separated string creates list
        self.result_type = None             # optional, multiplicity: 0|1
        self.request_id = None              # optional, multiplicity: 0|1
        self.output_format = None           # optional, multiplicity: 0|1
        self.output_schema = None           # optional, multiplicity: 0|1
        self.start_position = None          # optional, multiplicity: 0|1
        self.max_records = None             # optional, multiplicity: 0|1
        self.type_names = None              # mandatory, multiplicity: 1
        self.element_set_name = None        # mutually exclusive with element_name, multiplicity: 0|1
        self.element_name = []              # mutually exclusive with element_set_name, multiplicity: *
        self.constraint_language = None     # optional, multiplicity: 0|1
        self.constraint = None              # optional, multiplicity: 0|1
        self.sort_by = None                 # optional, multiplicity: 0|1
        self.distributed_search = None      # optional, multiplicity: 0|1
        self.hop_count = None               # optional, multiplicity: 0|1
        self.response_handler = None        # optional, multiplicity: 0|1
        self.section = None                 # optional, multiplicity: 0|1, only for GetCapabilities

        # Fill default values, according to CSW specification
        self.output_schema = "http://www.opengis.net/cat/csw/2.0.2"
        self.result_type = "hits"
        self.output_format = "application/xml"
        self.start_position = 1
        self.max_records = 10
        self.distributed_search = False
        self.hop_count = 2

        self.parameter_map = {
            "request": "request",
            "service": "service",
            "version": "version",
            "namespace": "namespace",
            "resulttype": "result_type",
            "id": "request_id",
            "outputformat": "output_format",
            "outputschema": "output_schema",
            "startposition": "start_position",
            "maxrecords": "max_records",
            "typenames": "type_names",
            "elementsetname": "element_set_name",
            "elementname": "element_name",
            "constraintlanguage": "constraint_language",
            "constraint": "constraint",
            "sortby": "sort_by",
            "distributedsearch": "distributed_search",
            "hopcount": "hop_count",
            "responsehandler": "response_handler",
            "section": "section",
        }
        self._parse_parameters(param_dict)

    def _parse_parameters(self, params_dict: dict):
        """ Parses a parameter dictionary into the object

        Args:
            params_dict (dict): The parameter key-value dict
        Returns:

        """
        # Parse all parameters automatically by resolving the parameter_map
        for key, val in params_dict.items():
            key_lower = key.lower()
            param = self.parameter_map.get(key_lower, None)
            if not param:
                continue

            # Make sure no negative integers are passed
            try:
                val = int(val)
                if val < 0:
                    raise AssertionError("No negative values allowed!")
            except ValueError:
                pass
            setattr(self, param, val)

        # Transform listable parameters into lists
        listable_elements = ["element_name", "namespace"]
        for elem in listable_elements:
            attribute = getattr(self, elem)
            if isinstance(attribute, str):
                attribute = attribute.split(",")
                setattr(self, elem, attribute)

        # Check if range of values is acceptable
        if self.result_type not in RESULT_TYPE_CHOICES:
            raise ValueError(INVALID_PARAMETER_TEMPLATE.format(self.result_type, ", ".join(RESULT_TYPE_CHOICES)), "resultType")

        if self.element_set_name is not None and len(self.element_name) > 0:
            raise ValueError("Parameter 'ElementSetName' and 'ElementName' are mutually exclusive. You can only provide one!", "elementSetName")
        elif self.element_set_name and self.element_set_name not in ELEMENT_SET_CHOICES:
            raise ValueError(INVALID_PARAMETER_TEMPLATE.format(self.element_set_name, ", ".join(ELEMENT_SET_CHOICES)), "elementSetName")
        elif self.element_set_name is None and len(self.element_name) == 0:
            self.element_set_name = "full"  # default

        if self.version not in VERSION_CHOICES:
            raise ValueError(INVALID_PARAMETER_TEMPLATE.format(self.version, ", ".join(VERSION_CHOICES)), "version")

        # Check if constraint has to be transformed first!
        if self.constraint_language is not None and self.constraint_language.upper() != "CQL_TEXT":
            try:
                #self.constraint = transform_constraint_to_cql(self.constraint, self.constraint_language)
                self.constraint_language = "CQL_TEXT"
            except TypeError:
                raise ValueError("XML does not seem to be valid. Please check the CSW specification.", CONSTRAINT_LOCATOR)
        elif self.constraint is not None:
            pass
            # FIXME
            #xml_elem = xml_helper.parse_xml(self.constraint)
           # if xml_elem is not None:
            #    raise ValueError("XML found for constraint parameter but CQL_TEXT found for constraintlanguage. Please set your parameters correctly.", CONSTRAINT_LOCATOR)