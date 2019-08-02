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


def xml_to_string(xml_obj):
    enc = "UTF-8"
    return etree.tostring(xml_obj, encoding=enc, method="xml").decode()


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


def find_element_where_text(xml_obj, txt: str):
    """ Returns all elements that contain the given text

    Args:
        xml_obj: The xml element
        txt: The text the user is looking for
    Returns:
         The elements that contain the provided text
    """
    return xml_obj.xpath("//*[text()='{}']/parent::*".format(txt), namespaces=XML_NAMESPACES)


def find_element_where_attr(xml_obj, attr_name, attr_val):
    """ Returns all elements that contain the given text

    Args:
        xml_obj: The xml element
        attr_name: The attribute the user is looking for
        attr_val: The value the user is expecting there
    Returns:
         The elements that contain the provided text
    """
    return xml_obj.xpath("//*[@{}='{}']/parent::*".format(attr_name, attr_val), namespaces=XML_NAMESPACES)


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


def remove_element(xml_child):
    """ Removes a child xml element from its parent xml element

    Args:
        xml_child: The xml child object that shall be removed
    Returns:
         nothing
    """
    parent = xml_child.getparent()
    parent.remove(xml_child)


def add_subelement(xml_elem, tag_name):
    """ Creates a new xml element as a child of xml_elem with the name tag_name

    Args:
        xml_elem: The xml element
        tag_name: The tag name for the new element
    Returns:
         A new subelement of xml_elem
    """
    return etree.SubElement(xml_elem, tag_name)
