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
    """ Builder for OGC XML POST documents

    """
    def __init__(self, post_data: dict, post_body: str=None):
        """ Constructor

        Args:
            post_data (dict): The post data as a dict
            post_body (str): A previously existing post xml body
        """
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

        self.post_data = post_data  # post data in a dict
        self.post_body = post_body  # post data, that came as xml in a body

    def _get_POST_val(self, key: str):
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

    def _get_version_specific_namespaces(self, version_param: str, service_param: str):
        """ Returns a reduced namespace map.

        Overwrites the default reduced namespace depending on the given version

        Args:
            version_param (str): The version parameter
        Returns:
             default_ns (dict): A reduced namespace map
        """
        default_ns = {
            "ogc": XML_NAMESPACES["ogc"],
            "xsi": XML_NAMESPACES["xsi"],
            "ows": XML_NAMESPACES["ows"],
        }

        # check for service type depending differences
        if service_param == OGCServiceEnum.WFS.value.lower():
            default_ns["wfs"] = XML_NAMESPACES["wfs"]

        elif service_param == OGCServiceEnum.WMS.value.lower():
            default_ns["sld"] = XML_NAMESPACES["sld"]
            default_ns["wms"] = XML_NAMESPACES["wms"]
            default_ns["gml"] = XML_NAMESPACES["gml"]
            default_ns["se"] = XML_NAMESPACES["se"]

        else:
            # not happening
            pass

        # check for version depending differences
        if version_param == OGCServiceVersionEnum.V_2_0_0.value or version_param == OGCServiceVersionEnum.V_2_0_2.value:
            # WFS 2.0.0
            default_ns["wfs"] = "http://www.opengis.net/wfs/2.0"
            default_ns["fes"] = XML_NAMESPACES["fes"]

        return default_ns

    def build_POST_xml(self):
        """ Builds a POST xml document, according to the OGC WMS/WFS specifications.

        Returns:
            xml (str): The xml document
        """
        xml = None

        # decide which specification must be used for POST XML building
        version_param = self._get_POST_val("version")
        service_param = self._get_POST_val("service").lower()

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

        request_param = self._get_POST_val("request")

        if request_param == OGCOperationEnum.DESCRIBE_FEATURE_TYPE.value:
            xml = self._build_describe_feature_type_xml(service_param, version_param, request_param)
            
        elif request_param == OGCOperationEnum.GET_FEATURE.value:
            xml = self._build_get_feature_xml(service_param, version_param, request_param)
            
        elif request_param == OGCOperationEnum.LOCK_FEATURE.value:
            xml = self._build_lock_feature_xml(service_param, version_param, request_param)
            
        elif request_param == OGCOperationEnum.TRANSACTION.value:
            xml = self._build_transaction_xml()
            
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
        
        format_param = self._get_POST_val("format") or ""
        type_name_param = self._get_POST_val("typename")
        
        reduced_ns_map = self._get_version_specific_namespaces(version_param, service_param)

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

        format_param = self._get_POST_val("format") or ""
        type_name_param = self._get_POST_val("typename")
        filter_param = self._get_POST_val("filter")

        # check if the newer 'typeNames' instead of 'typeName' should be used
        type_name_identifier = "typeName"
        if version_param == OGCServiceVersionEnum.V_2_0_0.value or version_param == OGCServiceVersionEnum.V_2_0_2.value:
            type_name_identifier = "typeNames"

        reduced_ns_map = self._get_version_specific_namespaces(version_param, service_param)
        wfs_ns = reduced_ns_map["wfs"]

        root_attributes = {
            "service": service_param,
            "version": version_param,
            "outputFormat": format_param
        }
        root = etree.Element(_tag="{" + wfs_ns + "}" + request_param, nsmap=reduced_ns_map, attrib=root_attributes)

        # create the xml filter object from the filter string parameter
        filter_xml = xml_helper.parse_xml(filter_param)
        filter_xml_root = filter_xml.getroot()

        for t_n_param in type_name_param.split(","):
            query_attributes = {
                type_name_identifier: t_n_param
            }
            query_elem = xml_helper.create_subelement(root, "{" + wfs_ns + "}" + "Query", attrib=query_attributes)

            # add the filter xml object as subobject to the query to use e.g. the spatial restriction
            xml_helper.add_subelement(query_elem, filter_xml_root)

        xml = xml_helper.xml_to_string(root)

        return xml
    
    def _build_transaction_xml(self):
        """ Returns the POST request XML for a Transaction request

        Since the Transaction request will already be transmitted as a POST xml, we simply return this one.
        No need for further xml building.

        Args:

        Returns:
             xml (str): The xml document
        """
        return self.post_body
    
    def _build_lock_feature_xml(self, service_param: str, version_param: str, request_param: str):
        """ Returns the POST request XML for a Lock request

        Args:
            service_param (str): The service param
            version_param (str): The version param
            request_param (str): The request param
        Returns:
             xml (str): The xml document
        """
        xml = ""

        lock_action_param = self._get_POST_val("lockAction") or ""
        type_name_param = self._get_POST_val("typename")
        filter_param = self._get_POST_val("filter")

        reduced_ns_map = self._get_version_specific_namespaces(version_param, service_param)

        root_attributes = {
            "service": service_param,
            "version": version_param,
            "lockAction": lock_action_param
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

    def _build_WMS_1_0_0_xml(self, service_param: str, version_param: str, request_param: str):
        """ Returns the POST xml document for a WMS 1.0.0

        PLEASE NOTE: THE SPECIFICATION FOR WMS 1.0.0 DOES NOT PROVIDE INFORMATION ABOUT THE SCHEMA OF A WMS POST REQUEST.
        AS LONG AS THERE IS NO SUCH DATA, THIS FUNCTION IS A PLACEHOLDER FOR FUTURE IMPLEMENTATION.

        Args:
            service_param (str): The service param
            version_param (str): The version param
            request_param (str): The request param
        Returns:
             xml (str): The xml document
        """
        xml = ""

        if request_param == OGCOperationEnum.GET_MAP.value.lower():
            xml = self._build_WMS_get_map_1_0_0_xml(service_param, version_param, request_param)
        else:
            xml = self._build_WMS_get_feature_info_1_0_0_xml(service_param, version_param, request_param)

        return xml

    def _build_WMS_get_map_1_0_0_xml(self, service_param: str, version_param: str, request_param: str):
        """ Returns the POST xml document for a WMS 1.0.0

        PLEASE NOTE: THE SPECIFICATION FOR WMS 1.0.0 DOES NOT PROVIDE INFORMATION ABOUT THE SCHEMA OF A WMS POST REQUEST.
        AS LONG AS THERE IS NO SUCH DATA, THIS FUNCTION IS A PLACEHOLDER FOR FUTURE IMPLEMENTATION.

        Args:
            service_param (str): The service param
            version_param (str): The version param
            request_param (str): The request param
        Returns:
             xml (str): The xml document
        """
        xml = ""
        return xml

    def _build_WMS_get_feature_info_1_0_0_xml(self, service_param: str, version_param: str, request_param: str):
        """ Returns the POST xml document for a WMS 1.0.0

        PLEASE NOTE: THE SPECIFICATION FOR WMS 1.0.0 DOES NOT PROVIDE INFORMATION ABOUT THE SCHEMA OF A WMS POST REQUEST.
        AS LONG AS THERE IS NO SUCH DATA, THIS FUNCTION IS A PLACEHOLDER FOR FUTURE IMPLEMENTATION.

        Args:
            service_param (str): The service param
            version_param (str): The version param
            request_param (str): The request param
        Returns:
             xml (str): The xml document
        """
        xml = ""
        return xml

    def _build_WMS_1_1_1_xml(self, service_param: str, version_param: str, request_param: str):
        """ Returns the POST xml document for a WMS 1.1.1

        PLEASE NOTE:
        THE SPECIFICATION FOR WMS 1.1.1 EXPLICITLY STATES, THAT A WMS HAS TO BE REQUESTED USING HTTP GET.
        THERE IS NO INDICATION OF ANY SUPPORT OF NON-SLD WMS 1.1.1 FOR USING POST XML DOCUMENTS.

        Args:
            service_param (str): The service param
            version_param (str): The version param
            request_param (str): The request param
        Returns:
             xml (str): The xml document
        """
        xml = ""
        return xml

    def _build_WMS_1_3_0_xml(self, service_param: str, version_param: str, request_param: str):
        """ Returns the POST xml document for a WMS 1.1.1

        PLEASE NOTE:
        THE SPECIFICATION FOR WMS 1.3.0 EXPLICITLY STATES, A WMS POST REQUEST HAS TO BE MADE USING XML.

        Args:
            service_param (str): The service param
            version_param (str): The version param
            request_param (str): The request param
        Returns:
             xml (str): The xml document
        """
        xml = ""

        if request_param == OGCOperationEnum.GET_MAP.value:
            xml = self._build_get_map_1_3_0_xml(service_param, version_param, request_param)
        elif request_param == OGCOperationEnum.GET_FEATURE_INFO:
            xml = self._build_get_feature_info_1_3_0_xml(service_param, version_param, request_param)
        else:
            # Should not happen
            pass

        return xml

    def _build_get_map_1_3_0_xml(self, service_param: str, version_param: str, request_param: str):
        """ Returns the POST request XML for a GetMap request

        Examples can be found here:

        http://schemas.opengis.net/sld/1.1/example_getmap.xml
        https://www.how2map.com/2013/10/geoserver-getmap-with-http-post.html

        Args:
            service_param (str): The service param
            version_param (str): The version param
            request_param (str): The request param
        Returns:
             xml (str): The xml document
        """
        xml = ""

        format_param = self._get_POST_val("format") or ""
        width_param = self._get_POST_val("width")
        height_param = self._get_POST_val("height")
        layers_param = self._get_POST_val("layer")
        bbox_param = self._get_POST_val("bbox")
        srs_param = self._get_POST_val("srs")

        reduced_ns_map = self._get_version_specific_namespaces(version_param, service_param)

        root_attributes = {
            "version": version_param
        }
        root = etree.Element(_tag=request_param, nsmap=reduced_ns_map, attrib=root_attributes)

        # Add <StyledLayerDescriptor> element with layer elements
        styled_layer_descriptor = etree.Element("StyledLayerDescriptor", {"version": version_param}, reduced_ns_map)
        for layer in layers_param.split(","):
            named_layer_elem = etree.Element("NamedLayer")

            name_elem = etree.Element("{" + reduced_ns_map["se"] + "}Name")
            name_elem.text = layer

            xml_helper.add_subelement(named_layer_elem, name_elem)
            xml_helper.add_subelement(styled_layer_descriptor, named_layer_elem)
        xml_helper.add_subelement(root, styled_layer_descriptor)

        # Add <CRS> element
        crs_elem = etree.Element("CRS")
        crs_elem.text = srs_param
        xml_helper.add_subelement(root, crs_elem)

        # Add <BoundingBox> element
        if bbox_param is not None:
            bbox_elem = etree.Element("BoundingBox")
            lower_corner_elem = etree.Element("ows:LowerCorner")
            upper_corner_elem = etree.Element("ows:UpperCorner")

            bbox_params_list = bbox_param.split(",")
            lower_corner_elem.text = "{} {}".format(bbox_params_list[0], bbox_params_list[1])
            upper_corner_elem.text = "{} {}".format(bbox_params_list[2], bbox_params_list[3])

            xml_helper.add_subelement(bbox_elem, lower_corner_elem)
            xml_helper.add_subelement(bbox_elem, upper_corner_elem)
            xml_helper.add_subelement(root, bbox_elem)

        # Add <Output> element
        output_elem = etree.Element("Output")
        size_elem = etree.Element("Size")
        width_elem = etree.Element("Width")
        width_elem.text = width_param
        height_elem = etree.Element("Height")
        height_elem.text = height_param
        xml_helper.add_subelement(size_elem, width_elem)
        xml_helper.add_subelement(size_elem, height_elem)
        format_elem = etree.Element("wms:Format")
        format_elem.text = format_param

        xml_helper.add_subelement(output_elem, size_elem)
        xml_helper.add_subelement(output_elem, format_elem)
        xml_helper.add_subelement(root, output_elem)

        xml = xml_helper.xml_to_string(root)

        return xml

    def _build_get_feature_info_1_3_0_xml(self, service_param: str, version_param: str, request_param: str):
        """ Returns the POST request XML for a GetFeatureInfo request

        PLEASE NOTE:
        THE SPECIFICATION FOR WMS 1.3.0 DOES NOT PROVIDE INFORMATION ABOUT THE POST XML SCHEMA OF GetFeatureInfo.
        THIS IS A PLACEHOLDER, WHICH SHALL HOLD A FUTURE IMPLEMENTATION - IF NEEDED.

        Args:
            service_param (str): The service param
            version_param (str): The version param
            request_param (str): The request param
        Returns:
             xml (str): The xml document
        """
        xml = ""
        return xml
