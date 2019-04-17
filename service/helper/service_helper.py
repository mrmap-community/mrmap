"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 16.04.19

"""
import urllib

import datetime
from lxml import etree

from MapSkinner.settings import DEFAULT_SERVICE_VERSION
from service.helper.enums import VersionTypes, ServiceTypes
from service.helper.ogc.wms import OGCWebMapService
from service.models import ServiceType, Service, WMS, ServiceMetadata, ContentMetadata, Layer


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


def __convert_layer_recursive(layers, service_type):
    # iterate over all layers
    for layer_obj in layers:
        layer = Layer()
        layer.title = layer_obj.title
        layer.servicetype = service_type
        layer.created_on = datetime.time()
        layer.abstract = layer_obj.abstract
        layer.is_available = False
        layer.availability = 0.0
        layer.hits = 0
        layer.parent = None
        layer.is_queryable = layer_obj.is_queryable
        layer.is_cascaded = layer_obj.is_cascaded
        layer.is_opaque = layer_obj.is_opaque
        layer.scale_min = layer_obj.capability_scale_hint.get("min")
        layer.scale_max = layer_obj.capability_scale_hint.get("max")



def convert_wms_to_model(wms_obj: OGCWebMapService):
    # create all needed database models
    service_type = ServiceType()
    service = WMS()
    service_metadata = ServiceMetadata()
    content_metadata = ContentMetadata()
    reference_systems = []
    layers = []
    keywords = []

    # fill objects
    service_type.version = wms_obj.service_version.value
    service_type.name = wms_obj.service_type.value

    service.title = wms_obj.service_identification_title
    service.abstract = wms_obj.service_identification_abstract
    service.created_on = datetime.time()
    service.availability = 0.0
    service.is_available = False
    service.servicetype = service_type
    # service.published_for = 0

    service_metadata.contact_person = wms_obj.service_provider_responsibleparty_individualname
    service_metadata.contact_email = wms_obj.service_provider_address_electronicmailaddress
    service_metadata.contact_organization = ""
    service_metadata.contact_person_position = wms_obj.service_provider_responsibleparty_positionname
    service_metadata.contact_phone = wms_obj.service_provider_telephone_voice
    service_metadata.city = wms_obj.service_provider_address_city
    service_metadata.address = wms_obj.service_provider_address
    service_metadata.post_code = wms_obj.service_provider_address_postalcode
    service_metadata.state_or_province = wms_obj.service_provider_address_state_or_province
    service_metadata.access_constraints = wms_obj.service_identification_accessconstraints
    service_metadata.created = datetime.time()
    service_metadata.is_active = False
    service_metadata.service_wms = service

    __convert_layer_recursive(layers=wms_obj.layers, service_type=service_type)


