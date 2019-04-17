"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 16.04.19

"""
import urllib
from lxml import etree

from MapSkinner.settings import DEFAULT_SERVICE_VERSION
from service.helper.enums import VersionTypes, ServiceTypes


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


def resolve_service_enum(service:str):
    """ Returns the matching Enum for a given service as string

    Args:
        service(str): The version as string
    Returns:
         The matching enum, otherwise None
    """
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
    for param_key, param_val in cap_url_dict.items():
        if param_key not in service_keywords:
            # append it back on the base uri
            ret_dict["base_uri"] += param_key + "=" + param_val

    return ret_dict


def parse_xml(xml: str):
    """ Returns the xml as iterable object

    Args:
        xml(str): The xml as string
    Returns:
        nothing
    """
    xml_bytes = xml.encode("UTF-8")
    xml_obj = etree.ElementTree(etree.fromstring(xml_bytes))
    return xml_obj


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
    except TypeError:
        pass
    return val