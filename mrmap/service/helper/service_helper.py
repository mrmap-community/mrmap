"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 16.04.19

"""
import urllib
from asyncio import current_task
from celery import current_task, states
from django.conf import settings
from django.db import transaction
from django.http import HttpResponse, HttpRequest
from MrMap.messages import SERVICE_DISABLED, PARAMETER_ERROR
from MrMap.utils import resolve_boolean_attribute_val
from service import tasks
from service.helper import xml_helper
from service.helper.common_connector import CommonConnector
from service.helper.enums import OGCServiceVersionEnum, OGCServiceEnum, OGCOperationEnum, DocumentEnum
from service.helper.epsg_api import EpsgApi
from service.helper.ogc.csw import OGCCatalogueService
from service.helper.ogc.wfs import OGCWebFeatureServiceFactory
from service.helper.ogc.wms import OGCWebMapServiceFactory
from service.models import Service, ExternalAuthentication, Document, Metadata
from service.helper.crypto_handler import CryptoHandler
from service.settings import PROGRESS_STATUS_AFTER_PARSING


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


def create_service(service_type,
                   version,
                   base_uri,
                   register_for_organization=None,
                   external_auth: ExternalAuthentication = None,
                   is_update_candidate_for: Service = None,
                   quantity: int = 1):
    """ Creates a database model from given service information and persists it.

    Due to the many-to-many relationships used in the models there is currently no way (without extending the models) to
    return an uncommitted database model object.

    Args;
        service_type: The type of service (wms, wfs)
        version: The version of the service type
        base_uri: The conne
        user (User): The performing user
        register_for_organization (Organization): The organization for which this service shall be registered
    Returns:

    """
    # todo: create one OGCServiceFactory...
    service = None
    if service_type is OGCServiceEnum.WMS:
        # create WMS object
        wms_factory = OGCWebMapServiceFactory()
        service = wms_factory.get_ogc_wms(version=version, service_connect_url=base_uri, external_auth=external_auth)

    elif service_type is OGCServiceEnum.WFS:
        # create WFS object
        wfs_factory = OGCWebFeatureServiceFactory()
        service = wfs_factory.get_ogc_wfs(version=version, service_connect_url=base_uri, external_auth=external_auth)

    elif service_type is OGCServiceEnum.CSW:
        # create CSW object
        # We need no factory pattern in here since we do not support different CSW versions
        service = OGCCatalogueService(service_connect_url=base_uri, service_version=version, external_auth=external_auth, service_type=service_type)

    else:
        # For future implementation
        pass

    service.get_capabilities()
    service.deserialize_from_capabilities()

    if current_task:
        current_task.update_state(
            state=states.STARTED,
            meta={
                'current': PROGRESS_STATUS_AFTER_PARSING,
                'phase': 'Persisting...',
            }
        )
    services = []
    for x in range(quantity):
        services.append(service.to_db(
            register_for_organization,
            is_update_candidate_for
        ))
    return services


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


def create_new_service(form, user):
    """ Creates a service from a filled RegisterNewServiceWizardPage2 form object.

    Args:
        form (RegisterNewServiceWizardPage2): The filled form instance
        user (MrMapUser): The performing user
    """
    external_auth = None
    if form.cleaned_data['service_needs_authentication']:
        external_auth = {
            "username": form.cleaned_data['username'],
            "password": form.cleaned_data['password'],
            "auth_type": form.cleaned_data['authentication_type']
        }

    uri_dict = {
        "base_uri": form.cleaned_data["uri"],
        "version": form.cleaned_data["ogc_version"],
        "service": form.cleaned_data["ogc_service"],
        "request": form.cleaned_data["ogc_request"],
    }

    return tasks.async_new_service.apply_async((form.cleaned_data['registering_for_organization'].pk,
                                                uri_dict,
                                                external_auth,
                                                form.cleaned_data['quantity'] if form.cleaned_data['quantity'] else 1),
                                               kwargs={'created_by_user_pk': user.pk},
                                               countdown=settings.CELERY_DEFAULT_COUNTDOWN)


def get_resource_capabilities(request: HttpRequest, md: Metadata):
    """ Logic for retrieving a capabilities document.

    If no capabilities document can be provided by the given parameter, a fallback document will be returned.

    Args:
        request:
        md:
    Returns:

    """
    from service.tasks import async_increase_hits
    stored_version = md.get_service_version().value
    # move increasing hits to background process to speed up response time!
    # todo: after refactoring of md.increase_hits() maybe we don't need to start async tasks... test it!!!
    async_increase_hits.delay(md.id)

    if not md.is_active:
        return HttpResponse(content=SERVICE_DISABLED, status=423)

    # check that we have the requested version in our database
    version_param = None
    version_tag = None

    request_param = None
    request_tag = None

    use_fallback = None

    for k, v in request.GET.dict().items():
        if k.upper() == "VERSION":
            version_param = v
            version_tag = k
        elif k.upper() == "REQUEST":
            request_param = v
            request_tag = k
        elif k.upper() == "FALLBACK":
            use_fallback = resolve_boolean_attribute_val(v)

    # No version parameter has been provided by the request - we simply use the one we have.
    if version_param is None or len(version_param) == 0:
        version_param = stored_version

    if version_param not in [data.value for data in OGCServiceVersionEnum]:
        # version number not valid
        return HttpResponse(content=PARAMETER_ERROR.format(version_tag), status=404)

    elif request_param is not None and request_param != OGCOperationEnum.GET_CAPABILITIES.value:
        # request not valid
        return HttpResponse(content=PARAMETER_ERROR.format(request_tag), status=404)

    else:
        pass

    if md.is_catalogue_metadata:
        doc = md.get_remote_original_capabilities_document(version_param)

    elif stored_version == version_param or use_fallback is True or not md.is_root():
        # This is the case if
        # 1) a version is requested, which we have in our database
        # 2) the fallback parameter is set explicitly
        # 3) a subelement is requested, which normally do not have capability documents

        # We can check the cache for this document or we need to generate it!
        doc = md.get_current_capability_xml(version_param)
    else:
        # we have to fetch the remote document
        # fetch the requested capabilities document from remote - we do not provide this as our default (registered) one
        xml = md.get_remote_original_capabilities_document(version_param)
        tmp = xml_helper.parse_xml(xml)

        if tmp is None:
            raise ValueError("No xml document was retrieved. Content was :'{}'".format(xml))
        # we fake the persisted service version, so the document setters will change the correct elements in the xml
        # md.service.service_type.version = version_param
        doc = Document(
            content=xml,
            metadata=md,
            document_type=DocumentEnum.CAPABILITY.value,
            is_original=True
        )
        doc.set_capabilities_secured(auto_save=False)

        if md.use_proxy_uri:
            doc.set_proxy(True, auto_save=False, force_version=version_param)
        doc = doc.content

    return doc