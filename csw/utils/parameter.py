"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 20.05.20

"""
from django.http import HttpRequest

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
            "requestid": "request_id",
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

            # Make sure no ' or " can be found inside the parameters
            val = val.replace("'", "").replace('"', "")

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
            raise AssertionError("Parameter '{}' invalid! Choices are '{}'".format(self.result_type, ",".join(RESULT_TYPE_CHOICES)))

        if self.element_set_name and self.element_name:
            raise AssertionError("Parameter 'ElementSetName' and 'ElementName' are mutually exclusive. You can only provide one!")
        elif self.element_set_name and self.element_set_name not in ELEMENT_SET_CHOICES:
            raise AssertionError("Parameter '{}' invalid! Choices are '{}'".format(self.element_set_name, ",".join(ELEMENT_SET_CHOICES)))
