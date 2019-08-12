"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 16.04.19

"""

import json
import urllib


from MapSkinner.settings import DEFAULT_SERVICE_VERSION, XML_NAMESPACES
from service.helper.common_connector import CommonConnector
from service.helper.enums import VersionTypes, ServiceTypes
from service.helper.epsg_api import EpsgApi
from service.helper.ogc.wfs import OGCWebFeatureServiceFactory
from service.helper.ogc.wms import OGCWebMapServiceFactory
from service.models import Layer, Metadata, MimeType, Service, CapabilityDocument
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


def activate_layer_recursive(root_layer, new_status):
    root_layer.metadata.is_active = new_status
    root_layer.metadata.save()
    for layer in root_layer.child_layer.all():
        activate_layer_recursive(layer, new_status)


def get_service_model_instance(service_type, version, base_uri, user, register_group, register_for_organization=None):
    """ Creates a database model from given service information and persists it.

    Due to the many-to-many relationships used in the models there is currently no way (without extending the models) to
    return an uncommitted database model object.

    Args;
        service_type: The type of service (wms, wfs)
        version: The version of the service type
        base_uri: The conne
        user (User): The performing user
        register_group (Group): The group which shall be used for registration
        register_for_organization (Organization): The organization for which this service shall be registered
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
        service = wms.create_service_model_instance(user, register_group, register_for_organization)
        ret_dict["raw_data"] = wms
    else:
        # create WFS object
        wfs_factory = OGCWebFeatureServiceFactory()
        wfs = wfs_factory.get_ogc_wfs(version=version, service_connect_url=base_uri)
        # let it load it's capabilities
        wfs.get_capabilities()
        wfs.create_from_capabilities()
        service = wfs.create_service_model_instance(user, register_group, register_for_organization)
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


def persist_capabilities_doc(service: Service, xml: str):
    """ Persists the capabilities document

    Args:
        service (Service): The service object which holds the related metadata
        xml (str): The xml document as string
    Returns:
         nothing
    """
    # save original capabilities document
    cap_doc = CapabilityDocument()
    cap_doc.original_capability_document = xml
    cap_doc.current_capability_document = xml
    cap_doc.related_metadata = service.metadata
    cap_doc.save()
