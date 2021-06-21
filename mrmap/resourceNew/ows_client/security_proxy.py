import time
import urllib
import io
from collections import OrderedDict
from copy import copy

from queue import Queue
from threading import Thread

from PIL import Image, ImageFont, ImageDraw
from cryptography.fernet import InvalidToken
from django.contrib.gis.gdal import SpatialReference
from django.core.exceptions import ObjectDoesNotExist
from django.db import connection
from django.db.models import Q
from lxml import etree

from django.contrib.gis.geos import Polygon, GEOSGeometry, Point, GeometryCollection, MultiLineString
from django.http import HttpRequest, HttpResponse, QueryDict
from lxml.etree import QName, _Element

from MrMap import utils
from MrMap.messages import PARAMETER_ERROR, TD_POINT_HAS_NOT_ENOUGH_VALUES, \
    SECURITY_PROXY_ERROR_MISSING_EXT_AUTH_KEY, SECURITY_PROXY_ERROR_WRONG_EXT_AUTH_KEY, \
    OPERATION_HANDLER_MULTIPLE_QUERIES_NOT_ALLOWED
from MrMap.settings import GENERIC_NAMESPACE_TEMPLATE, XML_NAMESPACES
from MrMap.utils import execute_threads
from resourceNew.models import Service
from service.helper import xml_helper
from service.helper.common_connector import CommonConnector
from service.helper.crypto_handler import CryptoHandler
from service.helper.enums import OGCOperationEnum, OGCServiceEnum, OGCServiceVersionEnum
from service.helper.epsg_api import EpsgApi
from service.serializer.ogc.request_builder import OGCRequestPOSTBuilder
from service.models import Metadata, FeatureType, Layer, ProxyLog, AllowedOperation
from service.settings import ALLLOWED_FEATURE_TYPE_ELEMENT_GEOMETRY_IDENTIFIERS, DEFAULT_SRS, DEFAULT_SRS_STRING, \
    MAPSERVER_SECURITY_MASK_FILE_PATH, MAPSERVER_SECURITY_MASK_TABLE, MAPSERVER_SECURITY_MASK_KEY_COLUMN, \
    MAPSERVER_SECURITY_MASK_GEOMETRY_COLUMN, MAPSERVER_LOCAL_PATH, DEFAULT_SRS_FAMILY, MIN_FONT_SIZE, FONT_IMG_RATIO, \
    RENDER_TEXT_ON_IMG, MAX_FONT_SIZE, ERROR_MASK_VAL, ERROR_MASK_TXT, service_logger


class SecurityProxy:
    """ Provides methods for handling an operation request for OGC services

    """

    def __init__(self, request: HttpRequest, allowed_operations: list):
        """ Constructor for OGCOperationRequestHandler

        Args:
            request (HttpRequest): An incoming request
        """
        self.request = request
        self.allowed_operations = allowed_operations



    def _create_secured_service_mask(self, metadata: Metadata, sec_ops: QueryDict):
        """ Creates call to local mapserver and returns the response

        Gets a mask image, which can be used to remove restricted areas from another image

        Args:
            metadata (Metadata): The metadata object
            sec_ops (QueryDict): SecuredOperation objects in a query dict
        Returns:
             bytes
        """
        masks = []
        width = int(self.width_param)
        height = int(self.height_param)
        try:
            for op in sec_ops:
                if op.allowed_area is None or op.allowed_area.empty:
                    return None
                request_dict = {
                    "map": MAPSERVER_SECURITY_MASK_FILE_PATH,
                    "version": "1.1.1",
                    "request": "GetMap",
                    "service": "WMS",
                    "format": "image/png",
                    "layers": "mask",
                    "srs": self.srs_param,
                    "bbox": self.axis_corrected_bbox_param,
                    "width": width,
                    "height": height,
                    "keys": "'{}'".format(op.id),
                    "table": MAPSERVER_SECURITY_MASK_TABLE,
                    "key_column": MAPSERVER_SECURITY_MASK_KEY_COLUMN,
                    "geom_column": MAPSERVER_SECURITY_MASK_GEOMETRY_COLUMN,
                }
                uri = "{}?{}".format(
                    MAPSERVER_LOCAL_PATH,
                    urllib.parse.urlencode(request_dict)
                )

                c = CommonConnector(url=uri)
                c.load()
                mask = Image.open(io.BytesIO(c.content))
                masks.append(mask)

            # Create empty final mask object
            mask = Image.new("RGBA", (width, height), (255, 0, 0, 0))

            # Combine all single masks into one!
            for m in masks:
                mask = Image.alpha_composite(m, mask)

            # Put combined mask on white background
            background = Image.new("RGB", (width, height), (255, 255, 255))
            background.paste(mask, mask=mask)
        except Exception as e:
            service_logger.exception(e)
            # If anything occurs during the mask creation, we have to make sure the response won't contain any
            # information at all.
            # So create an error mask
            background = Image.new("RGB", (width, height), (ERROR_MASK_VAL, ERROR_MASK_VAL, ERROR_MASK_VAL))

        return background

    def _create_masked_image(self, img: bytes, mask: bytes, as_bytes: bool = False):
        """ Creates a masked image from two image byte object

        Args:
            img (byte): The bytes of the image
            mask (byte): The bytes of the mask
            as_bytes (bool): Whether the image should be returned as Image object or as bytes
        Returns:
             img (Image): The masked image
        """
        try:
            # Transform byte-image to PIL-image object
            img = Image.open(io.BytesIO(img))
        except OSError:
            raise Exception("Could not create image! Content was:\n {}".format(img))
        try:
            # Create an alpha layer, which is needed for the compositing of image and mask
            alpha_layer = Image.new("RGBA", img.size, (255, 0, 0, 0))

            # Make sure we have any kind of mask
            if mask is None:
                # No bounding geometry for masking exist, so we just create a mask that does not mask anything
                mask = Image.new("RGB", img.size, (0, 0, 0))
            else:
                # There is a mask ...
                if isinstance(mask, bytes):
                    # ... but it is in bytes, so we need to transform it to a PIL-image object as well
                    mask = Image.open(io.BytesIO(mask))

                # Check if the mask is fine or indicates an error
                is_error_mask = mask.getpixel((0, 0))[0] == ERROR_MASK_VAL
                if is_error_mask:
                    # Create full-masking mask and create an access_denied_img
                    mask = Image.new("RGB", img.size, (255, 255, 255))
                    self.access_denied_img = self._create_image_with_text(img.width, img.height, ERROR_MASK_TXT)

        except OSError:
            raise Exception("Could not create image! Content was:\n {}".format(mask))

        # Make sure mask is in grayscale and has the exact same size as the requested image
        mask = mask.convert("L").resize(img.size)

        # save image format for restoring a few steps later
        img_format = img.format
        img = Image.composite(alpha_layer, img, mask)
        img.format = img_format

        # Add access_denied_img image
        # (contains info about which layers are restricted or if there was an error during mask creation)
        if self.access_denied_img is not None:
            old_format = img.format
            img = Image.alpha_composite(img, self.access_denied_img)
            img.format = old_format

        if as_bytes:
            out_bytes_stream = io.BytesIO()
            try:
                img.save(out_bytes_stream, img.format, quality=80)
                img = out_bytes_stream.getvalue()
            except IOError:
                # happens if a non-alpha channel format is requested, such as jpeg
                # replace alpha channel with white background
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                bg.save(out_bytes_stream, img.format, quality=80)
                img = out_bytes_stream.getvalue()
        return img

    def _filter_transaction_geometries(self, sec_ops: QueryDict):
        """ Checks whether the Transaction request can be allowed or not.

        Checks the SecuredOperations against geometries from the request

        Args:
            sec_ops (QueryDict): The SecuredOperations in a QueryDict object
        Returns:
             True|False
        """
        root_xml = None
        for sec_op in sec_ops:

            if sec_op.allowed_area.empty:
                # there is no allowed area defined, so this group is allowed to request everywhere. No filter needed
                return

            bounding_geom = sec_op.allowed_area.unary_union

            for trans_geom in self.transaction_geometries:
                xml_element = trans_geom.get("xml_element")
                root_xml = xml_element.getroottree().getroot()
                geometry = trans_geom.get("geometry")
                geometry.transform(bounding_geom.srid)
                if not bounding_geom.covers(geometry):
                    # If the geometry is not allowed, we remove the corresponding xml from the transaction request
                    xml_helper.remove_element(xml_element)
        self.POST_raw_body = xml_helper.xml_to_string(root_xml)

    def _resolve_layer_param_to_leaf_layers(self, metadata: Metadata):
        """ Replaces the original requested layer param with all (leaf) child layers identifier as param.

        This way we can make sure no layer is returned, that would not be allowed on a direct call.

        Args:
            metadata (Metadata): The metadata of the requested service
        Returns:
             nothing
        """
        leaf_layers = []
        if self.layers_param is None:
            return

        layer_identifiers = self.layers_param.split(",")

        layer_objs = Layer.objects.filter(
            parent_service__metadata=metadata,
            identifier__in=layer_identifiers
        )

        # Case 1: Only root layer is requested -> fast solution
        if layer_objs.count() == 1 and layer_objs[0].parent is None:
            # Yes, only the root layer has been requested
            # Order the sublayers by creation timestamp so the order of the layers in the request is correct (Top-Down)
            layers = Layer.objects.filter(
                parent_service__metadata=metadata,
                children=None
            ).order_by("created")
            leaf_layers += layers.values_list("identifier", flat=True)
        else:
            # Multiple layers have been requested -> slower solution
            for layer in layer_objs:
                leaf_layers += [leaf.identifier for leaf in layer.get_leafnodes()]

        if len(leaf_layers) > 0:
            self.layers_param = ",".join(leaf_layers)
        self.new_params_dict["LAYERS"] = self.layers_param

    def _extend_filter_by_spatial_restriction(self, sec_ops: QueryDict):
        """ Appends the spatial restriction filter element to an already existing filter

        Args:
            sec_ops (QueryDict: The secured operations, which hold the bounding geometries
        Returns:

        """
        bounding_geoms_filter_xml = []
        prefix = ""
        prefix_nsmap = {}
        if self.version_param == OGCServiceVersionEnum.V_2_0_0.value or self.version_param == OGCServiceVersionEnum.V_2_0_2.value:
            prefix = "{" + XML_NAMESPACES["fes"] + "}"
            prefix_nsmap = {
                "fes": XML_NAMESPACES["fes"]
            }

        # First get all polygons from the GeometryCollection and transform them according to the requested srs code
        for sec_op in sec_ops:
            bounding_geom_collection = sec_op.allowed_area
            if bounding_geom_collection is None:
                continue
            for bounding_geom in bounding_geom_collection.coords:
                coords = bounding_geom[0]
                geom = GEOSGeometry(Polygon(coords), bounding_geom_collection.srid)
                geom.transform(self.srs_code)
                bounding_geoms_filter_xml.append(geom)

        # Check whether the axis order has to be switched
        epsg_api = EpsgApi()
        switch_axis = epsg_api.check_switch_axis_order(self.service_type_param, self.version_param, self.srs_param)

        # Transform the polygon objects into a <Filter> xml document (as str)
        _filter = self._create_filter_xml_from_geometries(bounding_geoms_filter_xml, switch_axis_order=switch_axis)

        # check if there is already a filter, that came with the initial request. If so, we need to combine this
        # with our newly created one
        if self.filter_param is not None and len(_filter) > 0:
            request_filter_elem = xml_helper.parse_xml(self.filter_param).getroot()
            request_filter_elem_children = request_filter_elem.getchildren()
            backend_filter_elem = xml_helper.parse_xml(_filter).getroot()
            backend_filter_elem_children = backend_filter_elem.getchildren()

            if len(backend_filter_elem_children) > 0 and len(request_filter_elem_children) > 0:
                add_elem = etree.Element("{}And".format(prefix), nsmap=prefix_nsmap)
                for child in request_filter_elem_children:
                    xml_helper.add_subelement(add_elem, child)
                for child in backend_filter_elem_children:
                    xml_helper.add_subelement(add_elem, child)

                xml_helper.add_subelement(request_filter_elem, add_elem)
            _filter = xml_helper.xml_to_string(request_filter_elem)

        if len(_filter) == 0:
            _filter = None
        self.filter_param = _filter
        self.new_params_dict["FILTER"] = self.filter_param

    def get_allowed_operation_response(self):
        """ Calls the operation of a service if it is secured.
        """
        response = {
            "response": None,
            "response_type": ""
        }
        # TODO: check spatial filter of WFS - combination of BBOX GET Parameter and FE geometry filter
        # check_sec_ops = self.request_param in WMS_SECURED_OPERATIONS or self.request_param in WFS_SECURED_OPERATIONS

        # todo: geom should be the requested geometry as GEOSGeometry or a string of GeoJSON, WKT or HEXEWKB
        #  maybe we could get it from the self.x_y_coord
        #  have also a look on the lookup expressions for the GEOSGeometry field here:
        #  https://docs.djangoproject.com/en/3.1/ref/contrib/gis/geoquerysets/#std:fieldlookup-gis-contains

        all_sec_ops_for_user_by_operation = Q(secured_metadata__id__contains=self.metadata.id,
                                              allowed_groups__id__in=self.user_groups.values_list('id'),
                                              operations__operation__iexact=self.request_param)
        allowed_area_is_empty = Q(allowed_area=None)
        if self.bbox_param is not None:
            allowed_area_covers_bbox = Q(allowed_area__covers=self.bbox_param['geom'])
            allowed_area_intersects_bbox = Q(allowed_area__intersects=self.bbox_param['geom'])
            full_query_all = all_sec_ops_for_user_by_operation & allowed_area_intersects_bbox |\
                all_sec_ops_for_user_by_operation & allowed_area_is_empty
            full_query_wms_getfeatureinfo = all_sec_ops_for_user_by_operation & allowed_area_covers_bbox |\
                allowed_area_covers_bbox & allowed_area_is_empty
        else:
            full_query_all = all_sec_ops_for_user_by_operation
            full_query_wms_getfeatureinfo = all_sec_ops_for_user_by_operation

        # check if the metadata allows operation performing for certain groups
        # use combined filter
        is_allowed = AllowedOperation.objects.filter(full_query_all).exists()

        if not is_allowed:
            # this means the service is secured and the group has no access!
            return response

        # todo: move to needed sub if/else trees which needs this queryset
        sec_ops = AllowedOperation.objects.filter(all_sec_ops_for_user_by_operation)

        # WMS - 'GetFeatureInfo'
        if self.request_param.upper() == OGCOperationEnum.GET_FEATURE_INFO.value.upper():
            is_allowed = AllowedOperation.objects.filter(full_query_wms_getfeatureinfo).exists()

            if is_allowed:
                response = self.get_operation_response()

        # WMS - 'Map image'
        elif self.request_param.upper() == OGCOperationEnum.GET_MAP.value.upper():
            # We don't check any kind of is-allowed or not here.
            # Instead, we simply fetch the map image as it is and mask it, using our secured operations geometry.
            # To improve the performance here, we use a multithreaded approach, where the original map image and the
            # mask are generated at the same time. This speed up the process by ~30%!
            thread_list = []
            results = Queue()
            thread_list.append(
                Thread(target=lambda r: r.put(self.get_operation_response(), connection.close()), args=(results,))
            )
            thread_list.append(
                Thread(target=lambda r, m, s: r.put(self._create_secured_service_mask(m, s), connection.close()),
                       args=(results, self.metadata, sec_ops))
            )
            execute_threads(thread_list)

            # Since we have no idea which result will be on which position in the query
            response = None
            mask = None
            while not results.empty():
                result = results.get()
                if isinstance(result, dict):
                    # the img response!
                    response = result
                else:
                    mask = result

            img = response.get("response", "")
            img_format = response.get("response_type", "")

            response["response"] = self._create_masked_image(img, mask, as_bytes=True)
            response["response_type"] = img_format

        # WMS - 'Legend image'
        elif self.request_param.upper() == OGCOperationEnum.GET_LEGEND_GRAPHIC.value.upper():
            response = self.get_operation_response()

        # WFS - 'GetFeature'
        elif self.request_param.upper() == OGCOperationEnum.GET_FEATURE.value.upper():
            self._bbox_to_filter()
            self._extend_filter_by_spatial_restriction(sec_ops)
            response = self.get_operation_response()

        # WFS - 'DescribeFeatureType'
        elif self.request_param.upper() == OGCOperationEnum.DESCRIBE_FEATURE_TYPE.value.upper():
            response = self.get_operation_response()

        # WFS - 'Transaction'
        elif self.request_param.upper() == OGCOperationEnum.TRANSACTION.value.upper():
            self._filter_transaction_geometries(sec_ops)
            response = self.get_operation_response(post_xml_body=self.POST_raw_body)

        return response

    def get_operation_response(self, uri: str = None, post_data: dict = None, proxy_log: ProxyLog = None,
                               post_xml_body: str = None):
        """ Performs the request.

        This may be called after the security checks have passed or otherwise if no security checks had to be done.

        Args:
            uri (str): The operation uri
            proxy_log (ProxyLog): The logging object
            post_data(dict): A key-value dict of the POST data
            post_xml_body (str): A post xml body
        Returns:
             The xml response
        """

        # First try to perform a regular GET call
        if uri is None:
            uri = self._create_GET_uri()

        # Check if GET wouldn't work due to the length limitation of 2048 characters
        force_post = False
        if len(uri) > 2048:
            force_post = True

        # If we had a request incoming as GET and we do not need to switch to perform a POST, due to the length, we
        # are good to go!
        if self.request_is_GET and not force_post:
            c = CommonConnector(url=uri, external_auth=self.external_auth)
            c.load()

        # Otherwise we need to perform a POST request
        else:
            # Create a CommonConnector object using the post uri
            c = CommonConnector(url=self.post_uri, external_auth=self.external_auth)

            # If a post_body xml is given, we always prefer this over post_data
            if post_xml_body is not None:
                post_content = post_xml_body

            # ... so we do not have any xml post body content. If no other post_data content was provided as variable
            # we will construct our own post_data!
            elif post_data is None:
                post_content = self._create_POST_data()  # get default POST as dict content

            # Fallback - this would only happen if absolutely no parameters were given to this function
            else:
                post_content = post_data

            # There are two ways to post data to a server in the OGC service world:
            # 1)    Using x-www-form-urlencoded (mostly used in todays world)
            # 2)    Using a raw post body, which contains a xml (old style, used by some GIS servers)
            #
            # We try to perform 1)
            # It may happen, that some GIS servers can not handle the x-www-form-urlencoded content, so we need to
            # create a XML document, based on our post_content, and try to post again!
            c.post(post_content)
            try_again_code_list = [500, 501, 502, 504,
                                   510]  # if one of these codes will be returned, we need to try again using xml post

            if c.status_code is not None and c.status_code in try_again_code_list:
                # create xml from parameters according to specification
                request_builder = OGCRequestPOSTBuilder(post_content, self.POST_raw_body)
                post_xml = request_builder.build_POST_xml()
                c.post(post_xml)

        if c.status_code is not None and c.status_code != 200:
            raise Exception(c.status_code)

        ret_val = {
            "response": c.content,
            "response_type": c.http_external_headers.get("content-type", ("", ""))[1]
        }

        return ret_val
