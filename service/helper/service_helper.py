"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 16.04.19

"""
import json
import urllib

import datetime
import uuid

from django.db import transaction
from lxml import etree

from MapSkinner.settings import DEFAULT_SERVICE_VERSION
from service.helper.enums import VersionTypes, ServiceTypes
from service.helper.ogc.wms import OGCWebMapService, OGCWebMapServiceLayer
from service.models import ServiceType, Service, Layer, Keyword, Metadata, KeywordToMetadata, ReferenceSystem, \
    ReferenceSystemToMetadata
from structure.models import Organization, User, Group


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

def __find_parent_in_list(list, parent):
    if parent is None:
        return parent
    for elem in list:
        if isinstance(elem, Layer):
            if elem.identifier == parent.identifier:
                return elem
        else:
            continue


def __persist_layers(layers: list, service_type: ServiceType, wms: Service, creator: Group, publisher: Organization,
                              published_for: Organization, root_md: Metadata):
    pers_list = []
    # iterate over all layers
    for layer_obj in layers:
        layer = Layer()
        layer.identifier = layer_obj.identifier
        layer.servicetype = service_type
        layer.position = layer_obj.position
        layer.parent_layer = __find_parent_in_list(pers_list, layer_obj.parent)
        layer.is_queryable = layer_obj.is_queryable
        layer.is_cascaded = layer_obj.is_cascaded
        layer.is_opaque = layer_obj.is_opaque
        layer.scale_min = layer_obj.capability_scale_hint.get("min")
        layer.scale_max = layer_obj.capability_scale_hint.get("max")
        layer.bbox_lat_lon = json.dumps(layer_obj.capability_bbox_lat_lon)
        layer.created_by = creator
        layer.published_for = published_for
        layer.published_by = publisher
        layer.parent_service = wms
        layer.save()
        pers_list.append(layer)

        metadata = Metadata()
        metadata.title = layer_obj.title
        metadata.uuid = uuid.uuid4()
        metadata.abstract = layer_obj.abstract
        metadata.online_resource = root_md.online_resource
        metadata.service = layer
        metadata.contact_phone = root_md.contact_phone
        metadata.contact_person_position = root_md.contact_person_position
        metadata.contact_person = root_md.contact_person
        metadata.contact_organization = root_md.contact_organization
        metadata.contact_email = root_md.contact_email
        metadata.city = root_md.city
        metadata.post_code = root_md.post_code
        metadata.address = root_md.address
        metadata.state_or_province = root_md.state_or_province
        metadata.access_constraints = root_md.access_constraints
        metadata.is_active = False
        metadata.save()

        # handle keywords of this layer
        for kw in layer_obj.capability_keywords:
            keyword = Keyword.objects.get_or_create(keyword=kw)[0]
            kw_2_md = KeywordToMetadata()
            kw_2_md.metadata = metadata
            kw_2_md.keyword = keyword
            kw_2_md.save()

        # handle reference systems
        for sys in layer_obj.capability_srs:
            ref_sys = ReferenceSystem.objects.get_or_create(name=sys)[0]
            ref_sys_2_md = ReferenceSystemToMetadata()
            ref_sys_2_md.metadata = metadata
            ref_sys_2_md.reference_system = ref_sys
            ref_sys_2_md.save()


def persist_wms(wms_obj: OGCWebMapService):
    orga_published_for = Organization.objects.get(name="Testorganization")
    orga_publisher = Organization.objects.get(name="Testorganization")

    group = Group.objects.get(name="Testgroup")

    # fill objects
    service_type = ServiceType.objects.get_or_create(
        name=wms_obj.service_type.value,
        version=wms_obj.service_version.value
    )[0]

    service = Service()
    service.created_on = datetime.datetime.now()
    service.availability = 0.0
    service.is_available = False
    service.servicetype = service_type
    service.published_for = orga_published_for
    service.created_by = group
    service.save()

    # metadata
    metadata = Metadata()
    metadata.uuid = uuid.uuid4()
    metadata.title = wms_obj.service_identification_title
    metadata.abstract = wms_obj.service_identification_abstract
    metadata.online_resource = wms_obj.service_provider_onlineresource_linkage
    metadata.service = service
    metadata.is_root = True
    ## contact
    metadata.contact_person = wms_obj.service_provider_responsibleparty_individualname
    metadata.contact_email = wms_obj.service_provider_address_electronicmailaddress
    metadata.contact_organization = orga_publisher
    metadata.contact_person_position = wms_obj.service_provider_responsibleparty_positionname
    metadata.contact_phone = wms_obj.service_provider_telephone_voice
    metadata.city = wms_obj.service_provider_address_city
    metadata.address = wms_obj.service_provider_address
    metadata.post_code = wms_obj.service_provider_address_postalcode
    metadata.state_or_province = wms_obj.service_provider_address_state_or_province
    ## other
    metadata.access_constraints = wms_obj.service_identification_accessconstraints
    metadata.is_active = False
    metadata.save()

    __persist_layers(layers=wms_obj.layers, service_type=service_type, wms=service, creator=group, root_md=metadata,
                     publisher=orga_publisher, published_for=orga_published_for)


