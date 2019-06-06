"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 16.04.19

"""

import json
import urllib

from xml.dom import minidom
from xml.dom.minidom import Element, Text, Node

from django.shortcuts import get_object_or_404
from lxml import etree
from lxml.etree import XMLSyntaxError
from requests.exceptions import ProxyError

from MapSkinner.settings import DEFAULT_SERVICE_VERSION, XML_NAMESPACES
from service.helper.common_connector import CommonConnector
from service.helper.enums import VersionTypes, ServiceTypes
from service.helper.epsg_api import EpsgApi
from service.helper.ogc.wfs import OGCWebFeatureServiceFactory
from service.helper.ogc.wms import OGCWebMapServiceFactory
from service.models import Layer, Metadata, MimeType, Service
from MapSkinner.utils import sha256


def resolve_version_enum(version:str):
    """ Returns the matching Enum for a given version as string

    Args:
        version(str): The version as string
    Returns:
         The matching enum, otherwise None
    """
    for enum in VersionTypes:
        if enum.value == version:
            return enum
    return None


def resolve_service_enum(service: str):
    """ Returns the matching Enum for a given service as string

    Args:
        service(str): The version as string
    Returns:
         The matching enum, otherwise None
    """
    if service is None:
        return None
    for enum in ServiceTypes:
        if str(enum.value).upper() == service.upper():
            return enum
    return None


def split_service_uri(uri):
    """ Splits the service capabilities URI into its logical components

    Args:
        uri: The service capabilities uri
    Returns:
        ret_dict(dict): Contains the URI's components
    """
    ret_dict = {}

    cap_url_dict = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(uri).query))
    cap_url_query = urllib.parse.urlsplit(uri).query
    ret_dict["service"] = resolve_service_enum(cap_url_dict.get("SERVICE", None))
    ret_dict["request"] = cap_url_dict.get("REQUEST", None)
    ret_dict["version"] = resolve_version_enum(cap_url_dict.get("VERSION", DEFAULT_SERVICE_VERSION))
    ret_dict["base_uri"] = uri.replace(cap_url_query, "")
    service_keywords = ["REQUEST", "SERVICE", "VERSION"]
    additional_params = []
    for param_key, param_val in cap_url_dict.items():
        if param_key not in service_keywords:
            # append it back on the base uri
            additional_params.append(param_key + "=" + param_val)
    ret_dict["base_uri"] += "&".join(additional_params)

    return ret_dict


def get_xml_dom(xml: str):
    """ Creates a dom object from xml string

    This is needed for wrongly formatted input

    Args:
        xml: The xml string
    Returns:
    """
    dom = minidom.parseString(xml)
    return dom


def get_attributes_from_node(node: Node):
    """ Returns a dict containing all attributes of a given node

    Args:
        node (Node): The given node
    Returns:
         A dict containing all attributes found in the node
    """
    ret_dict = {}
    for attr_key, attr_val in node._attrs.items():
        ret_dict[attr_key] = attr_val.value
    return ret_dict


def get_text_from_node(node: Node):
    """ Get the text data from a node element

    Args:
        node (Node): The node
    Returns:
         The text of the node
    """
    text = []
    for child in node.childNodes:
        if isinstance(child, Text):
            text.append(child.data)
    return " ".join(text)


def get_node_from_node_list(node_list, name):
    """ Returns a single node from a given list of nodes

    Args:
        node_list: The list of nodes that shall be searched through
        name: The tag name of the node we are looking for
    Returns:
         The node if found, otherwise None
    """
    for element in node_list:
        if isinstance(element, Element):
            n_l = element.getElementsByTagName(name)
            if len(n_l) == 1:
                return n_l[0]
            else:
                return Element("None")


def find_node_recursive(node_list: list, name):
    """ Searches in the given node_list recursively for an element that matches the tag name of the parameter name

    Args:
        node_list (list): The list of the initial nodes. Normally you will put a single node (e.g. the root) inside a list in here
        name: The name of the element we are looking for
    Returns:
         Returns the element if found, None otherwise
    """
    for node in node_list:
        if isinstance(node, Text):
            continue
        if node.tagName == name:
            return node
        n = find_node_recursive(node_list=node.childNodes, name=name)
        if n.tagName != "None":
            return n
    return Element("None")


def parse_xml(xml):
    """ Returns the xml as iterable object

    Args:
        xml(str): The xml as string
    Returns:
        nothing
    """

    if not isinstance(xml, bytes):
        xml = xml.encode("UTF-8")
    try:
        xml_obj = etree.ElementTree(etree.fromstring(text=xml))
    except XMLSyntaxError:
        xml_obj = None
    return xml_obj


def resolve_keywords_array_string(keywords: str):
    """ Transforms the incoming keywords string into its single keywords and returns them in a list

    Args:
        keywords(str): The keywords as one string. Sometimes separates by ',', sometimes only by ' '
    Returns:
        The keywords in a nice list
    """

    # first make sure no commas are left
    keywords = keywords.replace(",", " ")
    key_list = keywords.split(" ")
    ret_list = []
    for key in key_list:
        key = key.strip()
        if len(key) > 0:
            ret_list.append(key)
    return ret_list


def resolve_none_string(val: str):
    """ To avoid 'none' or 'NONE' as strings, we need to resolve this to the NoneType

    Args:
        val(str): The potential none value as string
    Returns:
        None if the string is resolvable to None or the input parameter itself
    """
    val_u = val.upper()
    if val_u == "NONE":
        return None
    return val


def resolve_boolean_attribute_val(val):
    """ To avoid boolean values to be handled as strings, this function returns the boolean value of a string.

    If the provided parameter is not resolvable it will be returned as it was.

    Args:
        val:
    Returns:
         val
    """

    try:
        val = bool(int(val))
    except (TypeError, ValueError) as e:
        if isinstance(val, str):
            val_tmp = val.upper()
            if val_tmp == "FALSE":
                return False
            if val_tmp == "TRUE":
                return True
    return val


def get_feature_type_elements_xml(title, service_type_version, service_type, uri):
    connector = CommonConnector(url=uri)
    params = {
        "service": service_type,
        "version": service_type_version,
        "request": "DescribeFeatureType",
        "typeNames": title
    }
    try:
        connector.load(params=params)
        response = connector.content
        response = parse_xml(response)
    except ConnectionError:
        return None
    except ProxyError:
        return None
    return response


def try_get_single_element_from_xml(elem: str, xml_elem):
    """ Wraps a try-except call to fetch a single element from an xml element

    Returns the first element of a result set. If the programmer knows what he/she does there should be only on element.
    Returns None if there are none

    Args:
        elem:
        xml_elem:
    Returns:
         ret_val: The found element(s), otherwise None
    """

    tmp = try_get_element_from_xml(elem=elem, xml_elem=xml_elem)
    try:
        return tmp[0]
    except (IndexError, TypeError) as e:
        return None


def try_get_element_from_xml(elem: str, xml_elem):
    """ Wraps a try-except call to fetch elements from an xml element

    Args:
        elem:
        xml_elem:
    Returns:
         ret_val: The found element(s), otherwise None
    """
    ret_val = None
    try:
        ret_val = xml_elem.xpath(elem, namespaces=XML_NAMESPACES)
    except AttributeError:
        pass
    return ret_val


def try_get_attribute_from_xml_element(xml_elem, attribute: str, elem: str = None):
    """ Returns the requested attribute of an xml element

    Args:
        attribute:
        xml_elem:
        elem:
    Returns:
        A string if attribute was found, otherwise None
    """
    if elem is None:
        tmp = [xml_elem]
    else:
        tmp = try_get_element_from_xml(elem=elem, xml_elem=xml_elem)
    try:
        return tmp[0].get(attribute)
    except (IndexError, AttributeError) as e:
        return None


def try_get_text_from_xml_element(xml_elem, elem: str=None):
    """ Returns the text of an xml element

    Args:
        elem:
        xml_elem:
    Returns:
        A string if text was found, otherwise None
    """
    if elem is not None:
        xml_elem = try_get_single_element_from_xml(elem=elem, xml_elem=xml_elem)
    try:
        return xml_elem.text
    except AttributeError:
        return None


def find_parent_in_list(list, parent):
    """ A helper function which returns the parent of a layer from a given list

    Args:
        list:
        parent:
    Returns:
    """
    if parent is None:
        return parent
    for elem in list:
        if isinstance(elem, Layer):
            if elem.identifier == parent.identifier:
                return elem
        else:
            continue


def fetch_detail_view_layer(layer, layers_md_list: list):
    """ Outsources the gathering of layer detail information from the views.py

    Args:
        layer:
        layers_md_list:
    Returns:
    """
    res = {}
    md = get_object_or_404(Metadata, service=layer)
    formats = list(MimeType.objects.filter(service=layer))
    sub_layers = Layer.objects.filter(parent_layer=layer)
    f_l = {}
    for _format in formats:
        if f_l.get(_format.action, None) is None:
            f_l[_format.action] = []
        f_l[_format.action].append(_format.mime_type)
    layer.bbox_lat_lon = json.loads(layer.bbox_lat_lon)
    res["metadata"] = md
    res["layer"] = layer
    res["formats"] = f_l
    layers_md_list.append(res)


def generate_name(srs_list: list=[]):
    """ Generates a name made from a list of spatial reference systems

    Args:
        srs_list:
    Returns:
         A hash made from the srs elements
    """
    tmp = []
    epsg_api = EpsgApi()
    for srs in srs_list:
        id = epsg_api.get_real_identifier(srs)
        tmp.append(str(id))
    tmp = "".join(tmp)
    return sha256(tmp)


def change_layer_status_recursively(root_layer, new_status):
    root_layer.metadata.is_active = new_status
    root_layer.metadata.save()
    for layer in root_layer.child_layer.all():
        change_layer_status_recursively(layer, new_status)


def get_service_model_instance(service_type, version, base_uri, user):
    """ Creates a database model from given service information and persists it.

    Due to the many-to-many relationships used in the models there is currently no way (without extending the models) to
    return an uncommitted database model object.

    Args;
        service_type: The type of service (wms, wfs)
        version: The version of the service type
        base_uri: The conne
        user:
    Returns:

    """

    ret_dict = {}
    if service_type is ServiceTypes.WMS:
        # create WMS object
        wms_factory = OGCWebMapServiceFactory()
        wms = wms_factory.get_ogc_wms(version=version, service_connect_url=base_uri)
        # let it load it's capabilities
        wms.get_capabilities()
        wms.create_from_capabilities()
        service = wms.create_service_model_instance(user)
        ret_dict["raw_data"] = wms
    else:
        # create WFS object
        wfs_factory = OGCWebFeatureServiceFactory()
        wfs = wfs_factory.get_ogc_wfs(version=version, service_connect_url=base_uri)
        # let it load it's capabilities
        wfs.get_capabilities()
        wfs.create_from_capabilities()
        service = wfs.create_service_model_instance(user)
        ret_dict["raw_data"] = wfs
    ret_dict["service"] = service
    return ret_dict


def persist_service_model_instance(service: Service):
    """ Persists the service model instance

    Args:
        service: The service model instance
    Returns:
         Nothing
    """
    if service.servicetype.name == ServiceTypes.WMS.value:
        # create WMS object
        wms_factory = OGCWebMapServiceFactory()
        wms = wms_factory.get_ogc_wms(version=resolve_version_enum(service.servicetype.version))
        wms.persist_service_model(service)
    else:
        # create WFS object
        wfs_factory = OGCWebFeatureServiceFactory()
        wfs = wfs_factory.get_ogc_wfs(version=resolve_version_enum(service.servicetype.version))
        wfs.persist_service_model(service)


def capabilities_are_different(cap_url_1, cap_url_2):
    """ Loads two capabilities documents using uris and checks if they differ

    Args:
        cap_url_1: First capabilities url
        cap_url_2: Second capabilities url
    Returns:
         bool: True if they differ, false if they are equal
    """
    # load xmls
    connector = CommonConnector(cap_url_1)
    connector.load()
    xml_1 = connector.text
    connector = CommonConnector(cap_url_2)
    connector.load()
    xml_2 = connector.text

    # hash both and compare hashes
    xml_1_hash = sha256(xml_1)
    xml_2_hash = sha256(xml_2)

    return xml_1_hash != xml_2_hash
