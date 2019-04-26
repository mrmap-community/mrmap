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

from xml.dom import minidom
from xml.dom.minicompat import NodeList
from xml.dom.minidom import Element, Text, Node

from lxml import etree

from MapSkinner.settings import DEFAULT_SERVICE_VERSION
from service.helper.enums import VersionTypes, ServiceTypes
from service.helper.ogc.wms import OGCWebMapService
from service.models import ServiceType, Service, Layer, Keyword, Metadata, KeywordToMetadata, ReferenceSystem, \
    ReferenceSystemToMetadata, ServiceToFormat, Dimension
from structure.models import Organization, Group


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
    for param_key, param_val in cap_url_dict.items():
        if param_key not in service_keywords:
            # append it back on the base uri
            ret_dict["base_uri"] += param_key + "=" + param_val

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
        if node.tagName == name:
            return node
        n = find_node_recursive(node_list=node.childNodes, name=name)
        if n.tagName != "None":
            return n
    return Element("None")


def parse_xml(xml: str):
    """ Returns the xml as iterable object

    Args:
        xml(str): The xml as string
    Returns:
        nothing
    """
    xml_bytes = xml.encode("UTF-8")
    xml_obj = etree.ElementTree(etree.fromstring(text=xml_bytes))
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
    except TypeError:
        pass
    return val

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
        ret_val = xml_elem.xpath(elem)
    except AttributeError:
        pass
    return ret_val

def try_get_text_from_xml_element(elem: str, xml_elem):
    """ Returns the text of an xml element

    Args:
        elem:
        xml_elem:
    Returns:
        A string if text was found, otherwise None
    """
    tmp = try_get_element_from_xml(elem=elem, xml_elem=xml_elem)
    try:
        return tmp[0].text
    except IndexError:
        return None

def __find_parent_in_list(list, parent):
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


def __persist_layers(layers: list, service_type: ServiceType, wms: Service, creator: Group, publisher: Organization,
                              published_for: Organization, root_md: Metadata):
    """ Iterates over all layers given by the service and persist them, including additional data like metadata and so on.

    Args:
        layers (list): A list of layers
        service_type (ServiceType): The type of the service this function has to deal with
        wms (Service): The root or parent service which holds all these layers
        creator (Group): The group that started the registration process
        publisher (Organization): The organization that publishes the service
        published_for (Organization): The organization for which the first organization publishes this data (e.g. 'in the name of')
        root_md (Metadata): The metadata of the root service (parameter 'wms')
    Returns:
    """
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
        layer.get_styles_uri = layer_obj.get_styles_uri
        layer.get_legend_graphic_uri = layer_obj.get_legend_graphic_uri
        layer.get_feature_info_uri = layer_obj.get_feature_info_uri
        layer.get_map_uri = layer_obj.get_map_uri
        layer.describe_layer_uri = layer_obj.describe_layer_uri
        layer.get_capabilities_uri = layer_obj.get_capabilities_uri
        if layer_obj.dimension is not None and len(layer_obj.dimension) > 0:
            dim = Dimension()
            dim.layer = layer
            dim.name = layer_obj.dimension.get("name")
            dim.units = layer_obj.dimension.get("units")
            dim.default = layer_obj.dimension.get("default")
            dim.extent = layer_obj.dimension.get("extent")
            # ToDo: Refine for inherited and nearest_value and so on
            dim.save()
        layer.save()

        # iterate over all available mime types and actions
        for action, format_list in layer_obj.format_list.items():
            for _format in format_list:
                service_to_format = ServiceToFormat()
                service_to_format.service = layer
                service_to_format.action = action
                service_to_format.mime_type = _format
                service_to_format.save()
        # to keep an eye on all handled layers we need to store them in a temporary list
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
        for sys in layer_obj.capability_projection_system:
            ref_sys = ReferenceSystem.objects.get_or_create(name=sys)[0]
            ref_sys_2_md = ReferenceSystemToMetadata()
            ref_sys_2_md.metadata = metadata
            ref_sys_2_md.reference_system = ref_sys
            ref_sys_2_md.save()


def persist_wms(wms_obj: OGCWebMapService):
    """ Persists the web map service and all of its related content and data

    Args:
        wms_obj (OGCWebMapService): The non-database object, that holds all the wms data
    Returns:
    """
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


