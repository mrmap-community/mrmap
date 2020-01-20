"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 20.01.20

"""
from lxml import etree

from MapSkinner.messages import PARAMETER_ERROR
from MapSkinner.settings import XML_NAMESPACES, GENERIC_NAMESPACE_TEMPLATE

from service.helper import xml_helper
from service.helper.enums import OGCOperationEnum, OGCServiceVersionEnum, OGCServiceEnum


class OGCRequestPOSTBuilder:
    def __init__(self, post_data: dict):
        self.wms_operations = [
                OGCOperationEnum.GET_MAP,
                OGCOperationEnum.GET_FEATURE_INFO,
                OGCOperationEnum.DESCRIBE_LAYER,
                OGCOperationEnum.GET_LEGEND_GRAPHIC,
                OGCOperationEnum.GET_STYLES,
                OGCOperationEnum.PUT_STYLES,
            ]
        self.wfs_operations = [
                OGCOperationEnum.GET_FEATURE,
                OGCOperationEnum.TRANSACTION,
                OGCOperationEnum.LOCK_FEATURE,
                OGCOperationEnum.DESCRIBE_FEATURE_TYPE,
            ]

        self.post_data = post_data

    def _build_POST_val(self, key: str):
        """ Returns a value case insensitive

        Args:
            key (str): The key
        Returns:
             None | the value
        """
        for post_key, post_val in self.post_data.items():
            if post_key.upper() == key.upper():
                return post_val
        return None

    def _get_version_specific_namespaces(self, version_param: str):
        """ Returns a reduced namespace map.

        Overwrites the default reduced namespace depending on the given version

        Args:
            version_param (str): The version parameter
        Returns:
             default_ns (dict): A reduced namespace map
        """
        default_ns = {
            "wfs": XML_NAMESPACES["wfs"],
            "ogc": XML_NAMESPACES["ogc"],
            "xsi": XML_NAMESPACES["xsi"],
        }

        if version_param == OGCServiceVersionEnum.V_2_0_0 or version_param == OGCServiceVersionEnum.V_2_0_2:
            # WFS 2.0.0
            default_ns["wfs"] = "http://www.opengis.net/wfs/2.0"
        return default_ns

    def build_POST_xml(self):
        xml = None

        # decide which specification must be used for POST XML building
        version_param = self._build_POST_val("version")
        service_param = self._build_POST_val("service").lower()

        if version_param is None:
            raise KeyError(PARAMETER_ERROR.format("VERSION"))
        if service_param is None:
            raise KeyError(PARAMETER_ERROR.format("SERVICE"))

        if service_param == OGCServiceEnum.WFS.value.lower():
            # WFS 1.0.0 - 2.0.2 all have the same POST xml specification
            xml = self._build_WFS_xml(service_param, version_param)

        elif service_param == OGCServiceEnum.WMS.value.lower():
            if version_param == OGCServiceVersionEnum.V_1_0_0.value:
                xml = self._build_WMS_1_0_0_xml(service_param, version_param)
            elif version_param == OGCServiceVersionEnum.V_1_1_1.value:
                xml = self._build_WMS_1_1_1_xml(service_param, version_param)
            elif version_param == OGCServiceVersionEnum.V_1_3_0.value:
                xml = self._build_WMS_1_3_0_xml(service_param, version_param)
            else:
                raise KeyError(PARAMETER_ERROR.format(version_param))
        else:
            raise KeyError(PARAMETER_ERROR.format(service_param))

        return xml

    def _build_WFS_xml(self, service_param: str, version_param: str):
        """ Returns a POST request for a web feature service as xml
        
        Args:
            service_param (str): The service param 
            version_param (str): The version param 
        Returns:
             xml (str): The xml document
        """
        xml = ""

        request_param = self._build_POST_val("request")

        if request_param == OGCOperationEnum.DESCRIBE_FEATURE_TYPE.value:
            xml = self._build_describe_feature_type_xml(service_param, version_param, request_param)
            
        elif request_param == OGCOperationEnum.GET_FEATURE.value:
            xml = self._build_get_feature_xml(service_param, version_param, request_param)
            
        elif request_param == OGCOperationEnum.LOCK_FEATURE.value:
            xml = self._build_lock_feature_xml(service_param, version_param, request_param)
            
        elif request_param == OGCOperationEnum.TRANSACTION.value:
            xml = self._build_transaction_xml(service_param, version_param, request_param)
            
        else:
            raise KeyError(PARAMETER_ERROR.format(request_param))

        return xml
    
    def _build_describe_feature_type_xml(self, service_param: str, version_param: str, request_param: str):
        """ Returns the POST request XML for a DescribeFeatureType request
        
        Args:
            service_param (str): The service param 
            version_param (str): The version param 
            request_param (str): The request param 
        Returns:
             xml (str): The xml document
        """
        
        format_param = self._build_POST_val("format") or ""
        type_name_param = self._build_POST_val("typename")
        
        reduced_ns_map = self._get_version_specific_namespaces(version_param)

        root_attributes = {
            "service": service_param,
            "version": version_param,
            "outputFormat": format_param
        }
        root = etree.Element(_tag=request_param, nsmap=reduced_ns_map, attrib=root_attributes)
        for t_n_param in type_name_param.split(","):
            type_name_elem = etree.Element(_tag="TypeName")
            type_name_elem.text = t_n_param
            xml_helper.add_subelement(root, type_name_elem)

        xml = xml_helper.xml_to_string(root)

        return xml
    
    def _build_get_feature_xml(self, service_param: str, version_param: str, request_param: str):
        """ Returns the POST request XML for a GetFeature request

        Args:
            service_param (str): The service param
            version_param (str): The version param
            request_param (str): The request param
        Returns:
             xml (str): The xml document
        """
        xml = ""

        format_param = self._build_POST_val("format") or ""
        type_name_param = self._build_POST_val("typename")
        filter_param = self._build_POST_val("filter")

        reduced_ns_map = self._get_version_specific_namespaces(version_param)
        wfs_ns = reduced_ns_map["wfs"]

        root_attributes = {
            "service": service_param,
            "version": version_param,
            "outputFormat": format_param
        }
        root = etree.Element(_tag=request_param, nsmap=reduced_ns_map, attrib=root_attributes)

        # create the xml filter object from the filter string parameter
        filter_xml = xml_helper.parse_xml(filter_param)
        filter_xml_root = filter_xml.getroot()

        for t_n_param in type_name_param.split(","):
            query_attributes = {
                "typeName": t_n_param
            }
            query_elem = xml_helper.create_subelement(root, "Query", attrib=query_attributes)

            # add the filter xml object as subobject to the query to use e.g. the spatial restriction
            xml_helper.add_subelement(query_elem, filter_xml_root)

        xml = xml_helper.xml_to_string(root)

        return xml
    
    def _build_transaction_xml(self, service_param: str, version_param: str, request_param: str):
        xml = ""
        return xml
    
    def _build_lock_feature_xml(self, service_param: str, version_param: str, request_param: str):
        xml = ""
        return xml

    def _build_WMS_1_0_0_xml(self, service_param: str, version_param: str):
        xml = ""
        return xml

    def _build_WMS_1_1_1_xml(self, service_param: str, version_param: str):
        xml = ""
        return xml

    def _build_WMS_1_3_0_xml(self, service_param: str, version_param: str):
        xml = ""
        return xml
