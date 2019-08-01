"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 31.07.19

"""
from lxml import etree
from lxml.etree import XMLSyntaxError
from requests.exceptions import ProxyError

from MapSkinner.settings import XML_NAMESPACES
from service.helper.common_connector import CommonConnector


def parse_xml(xml: str, encoding=None):
    """ Returns the xml as iterable object

    Args:
        xml(str): The xml as string
    Returns:
        nothing
    """
    default_encoding = "UTF-8"
    if not isinstance(xml, bytes):
        if encoding is None:
            xml_b = xml.encode(default_encoding)
        else:
            xml_b = xml.encode(encoding)
    else:
        xml_b = xml
    try:
        xml_obj = etree.ElementTree(etree.fromstring(text=xml_b))
        if encoding != xml_obj.docinfo.encoding:
            # there might be problems e.g. with german Umlaute ä,ö,ü, ...
            # try to parse again but with the correct encoding
            return parse_xml(xml, xml_obj.docinfo.encoding)
    except XMLSyntaxError:
        xml_obj = None
    return xml_obj


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
        elem: The requested element tag name
        xml_elem: The current xml element
    Returns:
        A string if text was found, otherwise None
    """
    if elem is not None:
        xml_elem = try_get_single_element_from_xml(elem=elem, xml_elem=xml_elem)
    try:
        return xml_elem.text
    except AttributeError:
        return None


def write_text_to_element(xml_elem, elem: str=None, txt: str=None):
    """ Write new text to a xml element.

    Elem can be used to refer to a subelement of the current xml_elem

    Args:
        xml_elem: The current xml element
        elem (str): The requested element tag name
        txt (str): The new text for the element
    Returns:
         xml_elem: The modified xml element
    """
    if xml_elem is not None:
        if elem is not None:
            xml_elem = try_get_single_element_from_xml(elem=elem, xml_elem=xml_elem)
        xml_elem.text = txt
    return xml_elem
