"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 16.04.19

"""

import urllib
import io

from PIL import Image, ImageOps
from celery import Task
from django.contrib.gis.geos import GEOSGeometry, Polygon, Point
from django.http import HttpResponse, QueryDict

from MapSkinner.messages import SECURITY_PROXY_ERROR_PARAMETER, SECURITY_PROXY_NOT_ALLOWED
from service.helper import xml_helper
from service.helper.ogc.operation_request_handler import OperationRequestHandler
from service.settings import DEFAULT_SERVICE_VERSION, MAPSERVER_SECURITY_MASK_FILE_PATH, MAPSERVER_LOCAL_PATH, \
    MAPSERVER_SECURITY_MASK_TABLE, MAPSERVER_SECURITY_MASK_GEOMETRY_COLUMN, MAPSERVER_SECURITY_MASK_KEY_COLUMN
from service.helper.common_connector import CommonConnector
from service.helper.enums import VersionEnum, ServiceEnum
from service.helper.epsg_api import EpsgApi
from service.helper.ogc.wfs import OGCWebFeatureServiceFactory
from service.helper.ogc.wms import OGCWebMapServiceFactory
from service.models import Service, Metadata
from MapSkinner.utils import sha256
from structure.models import User


def resolve_version_enum(version:str):
    """ Returns the matching Enum for a given version as string

    Args:
        version(str): The version as string
    Returns:
         The matching enum, otherwise None
    """
    for enum in VersionEnum:
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
    for enum in ServiceEnum:
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
    service_keywords = ["REQUEST", "SERVICE", "VERSION"]
    for param_key, param_val in cap_url_dict.items():
        p = param_key.upper()
        if p not in tmp:
            tmp[p] = param_val
    cap_url_dict = tmp

    cap_url_query = urllib.parse.urlsplit(uri).query
    ret_dict["service"] = resolve_service_enum(cap_url_dict.get("SERVICE", None))
    ret_dict["request"] = cap_url_dict.get("REQUEST", None)
    ret_dict["version"] = resolve_version_enum(cap_url_dict.get("VERSION", DEFAULT_SERVICE_VERSION))
    ret_dict["base_uri"] = uri.replace(cap_url_query, "")
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


def get_service_model_instance(service_type, version, base_uri, user, register_group, register_for_organization=None, async_task: Task = None):
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
    if service_type is ServiceEnum.WMS:
        # create WMS object
        wms_factory = OGCWebMapServiceFactory()
        wms = wms_factory.get_ogc_wms(version=version, service_connect_url=base_uri)
        # let it load it's capabilities
        wms.get_capabilities()
        wms.create_from_capabilities(async_task=async_task)
        service = wms.create_service_model_instance(user, register_group, register_for_organization)
        ret_dict["raw_data"] = wms
    else:
        # create WFS object
        wfs_factory = OGCWebFeatureServiceFactory()
        wfs = wfs_factory.get_ogc_wfs(version=version, service_connect_url=base_uri)
        # let it load it's capabilities
        wfs.get_capabilities()

        # since we iterate through featuretypes, we can use async task here
        wfs.create_from_capabilities(async_task=async_task)
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
    if service.servicetype.name == ServiceEnum.WMS.value:
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


def get_operation_response(uri: str):
    """ Fetching method for security proxy.

    Args:
        uri (str): The operation uri
    Returns:
         The xml response
    """
    c = CommonConnector(url=uri)
    c.load()
    if c.status_code is not None and c.status_code != 200:
        raise Exception(c.status_code)
    return c.content


def check_get_feature_info_operation_access(x_y_param: Point, sec_ops: QueryDict):
    """ Checks whether the user given x/y Point parameter object is inside the geometry, which defines the allowed
    access for the GetFeatureInfo operation

    Args:
        x_y_param (Point): A Point object
        sec_ops (QueryDict): A QueryDict containing SecuredOperation objects
    Returns:
         Whether the Point is inside the geometry or not
    """

    # User is at least in one group that has access to this operation on this metadata.
    # Now check the spatial restriction!
    constraints = {}
    if x_y_param is not None:
        constraints["x_y"] = False

    for sec_op in sec_ops:
        if sec_op.bounding_geometry.empty:
            # there is no specific area, so this group is allowed to request everywhere
            constraints["x_y"] = True
            break
        total_bounding_geometry = sec_op.bounding_geometry.unary_union
        if x_y_param is not None:
            if total_bounding_geometry.covers(x_y_param):
                constraints["x_y"] = True

    return False not in constraints.values()


def get_secured_service_mask(metadata: Metadata, sec_ops: QueryDict, operation_handler: OperationRequestHandler):
    """ Creates call to local mapserver and returns the response

    Gets a mask image, which can be used to remove restricted areas from another image

    Args:
        metadata (Metadata): The metadata object
        sec_ops (QueryDict): SecuredOperation objects in a query dict
        operation_handler (OperationRequestHandler): Holds important information for this operation
    Returns:
         bytes
    """
    response = ""
    for op in sec_ops:
        if op.bounding_geometry.empty:
            return None
        request_dict = {
            "map": MAPSERVER_SECURITY_MASK_FILE_PATH,
            "version": "1.1.1",
            "request": "GetMap",
            "service": "WMS",
            "format": "image/png",
            "layers": "mask",
            "srs": operation_handler.srs_param,
            "bbox": operation_handler.bbox_param.get("bbox_param"),
            "width": operation_handler.width_param,
            "height": operation_handler.height_param,
            "keys": op.id,
            "table": MAPSERVER_SECURITY_MASK_TABLE,
            "key_column": MAPSERVER_SECURITY_MASK_KEY_COLUMN,
            "geom_column": MAPSERVER_SECURITY_MASK_GEOMETRY_COLUMN,
        }
        uri = "{}?{}".format(
            MAPSERVER_LOCAL_PATH,
            urllib.parse.urlencode(request_dict)
        )
        response = get_operation_response(uri)
    return response


def create_masked_image(img: bytes, mask: bytes, as_bytes: bool = False):
    """ Creates a masked image from two image byte object

    Args:
        img (byte): The bytes of the image
        mask (byte): The bytes of the mask
    Returns:
         img (Image): The masked image
    """
    try:
        img = Image.open(io.BytesIO(img))
    except OSError:
        raise Exception("Could not create image! Content was:\n {}".format(img))
    try:
        if mask is None:
            # no bounding geometry for masking exist, just create a mask that does nothing
            mask = Image.new("RGB", img.size, (0, 0, 0))
        else:
            mask = Image.open(io.BytesIO(mask))
    except OSError:
        raise Exception("Could not create image! Content was:\n {}".format(mask))
    mask = mask.convert("L").resize(img.size)
    mask = ImageOps.invert(mask)

    img.putalpha(mask)

    if as_bytes:
        outBytesStream = io.BytesIO()
        try:
            img.save(outBytesStream, img.format, optimize=True, quality=80)
            img = outBytesStream.getvalue()
        except IOError:
            # happens if a non-alpha channel format is requested, such as jpeg
            # replace alpha channel with white background
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            bg.save(outBytesStream, img.format, optimize=True, quality=80)
            img = outBytesStream.getvalue()
    return img


def check_get_feature_operation_access(operation_handler: OperationRequestHandler, sec_ops: QueryDict):
    """ Checks whether the GetFeature request can be allowed or not.

    Checks the SecuredOperations against bounding geometry from the request

    Args:
        operation_handler (OperationRequestHandler): The OperationRequestHandler object
        sec_ops (QueryDict): The SecuredOperations in a QueryDict object
    Returns:
         True|False
    """
    ret_val = False

    # GetFeature operation is a WFS operation, which means the given bbox parameter must not be in EPSG:4326!
    bounding_geom = operation_handler.bbox_param

    if bounding_geom is None:
        # check if the filter parameter holds a bbox OR a bounding polygon
        bounding_geom = operation_handler.get_bounding_geometry_from_filter_param()
        if bounding_geom is None:

            # the request is broken!
            raise Exception()

    else:
        bounding_geom = bounding_geom.get("geom")

    for sec_op in sec_ops:

        if sec_op.bounding_geometry.empty:
            # there is no allowed area defined, so this group is allowed to request everywhere
            ret_val = True
            break

        # union all geometries in the geometrycollection (bounding_geometry) into one geometry
        access_restricting_geom = sec_op.bounding_geometry.unary_union

        if access_restricting_geom.srid != bounding_geom.srid:
            # this may happen if another srs was provided per request parameter.
            # we need to transform one of the geometries into the srs of the other
            access_restricting_geom.transform(bounding_geom.srid)

        if access_restricting_geom.covers(bounding_geom):
            # we are fine, the bounding geometry covers the requested area completely!
            ret_val = True
            break

        elif access_restricting_geom.intersects(bounding_geom):
            # we are only partially inside the bounding geometry
            # -> we need to create the intersection between bbox and bounding geometry
            # This is only the case for WFS requests!
            operation_handler.set_intersected_allowed_geometry(bounding_geom.intersection(access_restricting_geom))
            ret_val = True

    return ret_val


def get_secured_operation_result(metadata: Metadata, operation_handler: OperationRequestHandler, user: User):
    """ Performs a security access check and returns the desired result or an http error response

    Performs different checks on the secured access of the resource, which are linked using SecuredOperation objects.

    Args;
        metadata (Metadata): The metadata which describes the resource
        GET_params (dict): Contains all relevant parameters from the request
        user (User): The performing user
        uri:
    Returns:
         HttpResponse
    """
    # check if the metadata allows operation performing for certain groups
    sec_ops = metadata.secured_operations.filter(
        operation__operation_name__iexact=operation_handler.request_param,
        allowed_group__in=user.groups.all(),
    )

    if sec_ops.count() == 0:
        # this means the service is secured but the no groups have access!
        return HttpResponse(status=500, content=SECURITY_PROXY_NOT_ALLOWED)
    else:
        allowed = False
        response = None

        # WMS - Features
        if operation_handler.request_param.upper() == "GETFEATUREINFO":
            allowed = check_get_feature_info_operation_access(operation_handler.x_y_param, sec_ops)
            if allowed:
                response = get_operation_response(operation_handler.uri)

        # WMS - 'Map image'
        elif operation_handler.request_param.upper() == "GETMAP":
            # allow the access anyway, since we mask the output
            allowed = True
            img = get_operation_response(operation_handler.uri)
            mask = get_secured_service_mask(metadata, sec_ops, operation_handler)
            response = create_masked_image(img, mask, as_bytes=True)

        # WFS
        elif operation_handler.request_param.upper() == "GETFEATURE":
            allowed = check_get_feature_operation_access(operation_handler, sec_ops)
            if allowed:
                response = get_operation_response(operation_handler.uri)

        if allowed:
            return HttpResponse(response, content_type="")
        else:
            return HttpResponse(status=500, content=SECURITY_PROXY_NOT_ALLOWED)