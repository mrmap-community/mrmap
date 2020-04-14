"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 16.04.19

"""
import json
import urllib

from celery import Task

from MapSkinner.messages import SERVICE_REMOVED
from service import tasks
from service.helper.common_connector import CommonConnector
from service.helper.enums import OGCServiceVersionEnum, OGCServiceEnum
from service.helper.epsg_api import EpsgApi
from service.helper.ogc.wfs import OGCWebFeatureServiceFactory
from service.helper.ogc.wms import OGCWebMapServiceFactory
from service.models import Service, ExternalAuthentication, Metadata, Layer, FeatureType
from service.helper.crypto_handler import CryptoHandler
from structure.models import PendingTask, MrMapGroup, MrMapUser
from users.helper import user_helper


def resolve_version_enum(version: str):
    """ Returns the matching Enum for a given version as string

    Args:
        version(str): The version as string
    Returns:
         The matching enum, otherwise None
    """
    for enum in OGCServiceVersionEnum:
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
    for enum in OGCServiceEnum:
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
    tmp = {}

    # remove duplicate parameters
    service_keywords = [
        "REQUEST",
        "SERVICE",
        "VERSION"
    ]
    for param_key, param_val in cap_url_dict.items():
        p = param_key.upper()
        if p not in tmp:
            tmp[p] = param_val

    cap_url_query = urllib.parse.urlsplit(uri).query
    ret_dict["service"] = resolve_service_enum(tmp.get("SERVICE", None))
    ret_dict["request"] = tmp.get("REQUEST", None)
    ret_dict["version"] = tmp.get("VERSION", None)
    ret_dict["base_uri"] = uri.replace(cap_url_query, "")
    additional_params = []

    # append additional parameters back to the base uri
    for param_key, param_val in cap_url_dict.items():
        if param_key.upper() not in service_keywords:
            additional_params.append(param_key + "=" + param_val)

    ret_dict["base_uri"] += "&".join(additional_params)
    return ret_dict


def prepare_original_uri_stump(uri: str):
    """ Prepares an original uri of a service to end on '?' or '&'.

    Some uris already contain a '?' since they have a query, others do not.

    Args:
        uri (str: The original uri
    Returns:
        uri (str): The prepared original uri
    """
    uri_parsed = urllib.parse.urlparse(uri)
    query = dict(urllib.parse.parse_qsl(uri_parsed.query))

    additional_char = ""
    if len(query) > 0:
        additional_char = "&"
    else:
        additional_char = "?"

    # Only add an additional_char if it isn't there already
    if uri[-1] != additional_char:
        uri += additional_char
    return uri


def resolve_keywords_array_string(keywords: str):
    """ Transforms the incoming keywords string into its single keywords and returns them in a list

    Args:
        keywords(str): The keywords as one string. Sometimes separates by ',', sometimes only by ' '
    Returns:
        The keywords in a nice list
    """
    ret_list = []

    if keywords is not None:
        # first make sure no commas are left
        keywords = keywords.replace(",", " ")
        key_list = keywords.split(" ")
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
    sec_handler = CryptoHandler()
    return sec_handler.sha256(tmp)


def get_service_model_instance(service_type, version, base_uri, user, register_group, register_for_organization=None, async_task: Task = None, external_auth: ExternalAuthentication = None):
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
    if service_type is OGCServiceEnum.WMS:
        # create WMS object
        wms_factory = OGCWebMapServiceFactory()
        wms = wms_factory.get_ogc_wms(version=version, service_connect_url=base_uri, external_auth=external_auth)
        # let it load it's capabilities
        wms.get_capabilities()
        wms.create_from_capabilities(async_task=async_task)
        service = wms.create_service_model_instance(user, register_group, register_for_organization)
        ret_dict["raw_data"] = wms
    else:
        # create WFS object
        wfs_factory = OGCWebFeatureServiceFactory()
        wfs = wfs_factory.get_ogc_wfs(version=version, service_connect_url=base_uri, external_auth=external_auth)
        # let it load it's capabilities
        wfs.get_capabilities()

        # since we iterate through featuretypes, we can use async task here
        wfs.create_from_capabilities(async_task=async_task, external_auth=external_auth)
        service = wfs.create_service_model_instance(user, register_group, register_for_organization)
        ret_dict["raw_data"] = wfs
    ret_dict["service"] = service
    return ret_dict


def persist_service_model_instance(service: Service, external_auth: ExternalAuthentication):
    """ Persists the service model instance

    Args:
        external_auth: The external authentication instance
        service: The service model instance
    Returns:
         Nothing
    """
    if service.servicetype.name == OGCServiceEnum.WMS.value:
        # create WMS object
        wms_factory = OGCWebMapServiceFactory()
        wms = wms_factory.get_ogc_wms(version=resolve_version_enum(service.servicetype.version))
        wms.persist_service_model(service, external_auth)
    else:
        # create WFS object
        wfs_factory = OGCWebFeatureServiceFactory()
        wfs = wfs_factory.get_ogc_wfs(version=resolve_version_enum(service.servicetype.version))
        wfs.persist_service_model(service, external_auth)


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
    xml_1 = connector.content
    connector = CommonConnector(cap_url_2)
    connector.load()
    xml_2 = connector.content

    sec_handler = CryptoHandler()

    # hash both and compare hashes
    xml_1_hash = sec_handler.sha256(xml_1)
    xml_2_hash = sec_handler.sha256(xml_2)

    return xml_1_hash != xml_2_hash


def create_new_service(form, user: MrMapUser):
    """ Creates a service from a filled RegisterNewServiceWizardPage2 form object.

    Returns the PendingTask record for the registration process

    Args:
        form (RegisterNewServiceWizardPage2): The filled form instance
        user (MrMapUser): The performing user
    Returns:
         pending_task_db (PendingTask): The PendingTask record for the registration
    """
    external_auth = None
    if form.cleaned_data['service_needs_authentication']:
        external_auth = {
            "username": form.cleaned_data['username'],
            "password": form.cleaned_data['password'],
            "auth_type": form.cleaned_data['authentication_type']
        }

    register_for_other_org = 'None'
    if form.cleaned_data['registering_for_other_organization'] is not None:
        register_for_other_org = form.cleaned_data['registering_for_other_organization'].id

    uri_dict = {
        "base_uri": form.cleaned_data["uri"],
        "version": form.cleaned_data["ogc_version"],
        "service": form.cleaned_data["ogc_service"],
        "request": form.cleaned_data["ogc_request"],
    }

    pending_task = tasks.async_new_service.delay(
        uri_dict,
        user.id,
        form.cleaned_data['registering_with_group'].id,
        register_for_other_org,
        external_auth
    )

    # create db object, so we know which pending task is still ongoing
    pending_task_db = PendingTask()
    pending_task_db.created_by = MrMapGroup.objects.get(
        id=form.cleaned_data['registering_with_group'].id)
    pending_task_db.task_id = pending_task.task_id
    pending_task_db.description = json.dumps({
        "service": form.cleaned_data['uri'],
        "phase": "Parsing",
    })

    pending_task_db.save()
    return pending_task_db


def remove_service(metadata: Metadata, user: MrMapUser):
    """ Removes a service, referenced by its metadata object

    Args:
        metadata (Metadata): The metadata object related to the service
        user (MrMapUser): The performing user
    Returns:
         Nothing
    """
    # Make sure performing user is part of the group which added the service once
    user_groups = user.get_groups()
    if metadata.created_by not in user_groups:
        raise PermissionError()
    # remove service and all of the related content
    user_helper.create_group_activity(metadata.created_by, user, SERVICE_REMOVED, metadata.title)

    # set service as deleted, so it won't be listed anymore in the index view until completely removed
    metadata.is_deleted = True
    metadata.save()

    service_type = metadata.get_service_type()
    if service_type == OGCServiceEnum.WMS.value:
        sub_elements = Layer.objects.filter(parent_service__metadata=metadata)
    elif service_type == OGCServiceEnum.WFS.value:
        sub_elements = FeatureType.objects.filter(parent_service__metadata=metadata)

    for sub_element in sub_elements:
        sub_metadata = sub_element.metadata
        sub_metadata.is_deleted = True
        sub_metadata.save()

    # call removing as async task
    tasks.async_remove_service_task.delay(metadata.service.id)
