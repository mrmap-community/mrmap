"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 05.12.19

"""
import urllib, io

from PIL import Image, ImageOps
from django.core.exceptions import ObjectDoesNotExist
from lxml import etree

from django.contrib.gis.geos import Polygon, GEOSGeometry, Point, GeometryCollection
from django.http import HttpRequest, HttpResponse, QueryDict
from lxml.etree import QName

from MapSkinner.messages import SECURITY_PROXY_ERROR_PARAMETER
from MapSkinner.settings import GENERIC_NAMESPACE_TEMPLATE, XML_NAMESPACES
from service.helper import xml_helper
from service.helper.common_connector import CommonConnector
from service.helper.enums import ServiceOperationEnum, ServiceEnum, VersionEnum
from service.models import Metadata, FeatureType
from service.settings import ALLLOWED_FEATURE_TYPE_ELEMENT_GEOMETRY_IDENTIFIERS, DEFAULT_SRS, DEFAULT_SRS_STRING, \
    MAPSERVER_SECURITY_MASK_FILE_PATH, MAPSERVER_SECURITY_MASK_TABLE, MAPSERVER_SECURITY_MASK_KEY_COLUMN, \
    MAPSERVER_SECURITY_MASK_GEOMETRY_COLUMN, MAPSERVER_LOCAL_PATH
from users.helper import user_helper


class OGCOperationRequestHandler:
    """ Provides methods for handling an operation request for OGC services

    """

    def __init__(self, request: HttpRequest, metadata: Metadata, uri: str = None):
        self.uri = uri

        # check what type of request we are facing
        self.request_is_GET = request.method == "GET"
        self.original_params_dict = {}  # contains the original, unedited parameters
        self.new_params_dict = {}  # contains the parameters, which could be still original or might have changed during method processing

        self.request_param = None  # refers to param 'REQUEST'
        self.layer_param = None  # refers to param 'LAYERS'
        self.x_y_param = [None, None]  # refers to param 'X/Y' (WMS 1.0.0), 'X, Y' (WMS 1.1.1), 'I,J' (WMS 1.3.0)
        self.bbox_param = None  # refers to param 'BBOX'
        self.srs_param = None  # refers to param 'SRS' (WMS 1.0.0 - 1.1.1) and 'CRS' (WMS 1.3.0)
        self.srs_code = None  # only the srsid as int
        self.format_param = None  # refers to param 'FORMAT'
        self.version_param = None  # refers to param 'VERSION'
        self.filter_param = None  # refers to param 'FILTER' (WFS)
        self.width_param = None  # refers to param 'WIDTH' (WMS)
        self.height_param = None  # refers to param 'HEIGHT' (WMS)
        self.type_name_param = None  # refers to param 'TYPENAME' (WFS)
        self.geom_property_name = None  # will be set, if type_name_param is not None
        self.POST_raw_body = None  # refers to the body content of a Transaction operation
        self.transaction_geometries = None  # contains all geometries that shall be INSERTed or UPDATEd by a  Transaction operation

        self.intersected_allowed_geometry = None

        if self.request_is_GET:
            self.original_params_dict = request.GET.dict()
        else:
            self.original_params_dict = request.POST.dict()

        if len(self.original_params_dict) == 0:
            # Possible, if no GET query parameter or no x-www-form-urlencoded POST values have been given
            # In this case, all the information can be found inside a xml document in the POST body, that has to be parsed now.
            self._parse_POST_xml_body(request.body)

        # fill new_params_dict with upper case keys from original_params_dict
        for key, val in self.original_params_dict.items():
            self.new_params_dict[key.upper()] = val

        # extract parameter attributes from params dict
        for key, val in self.new_params_dict.items():
            if key == "REQUEST":
                self.request_param = val
            elif key == "LAYER":
                self.layer_param = val
            elif key == "BBOX":
                self.bbox_param = val
            elif key == "X" or key == "I":
                self.x_y_param[0] = val
            elif key == "Y" or key == "J":
                self.x_y_param[1] = val
            elif key == "VERSION":
                self.version_param = val
            elif key == "FORMAT":
                self.format_param = val
            elif key == "SRS" or key == "CRS":
                self.srs_param = val
                self.srs_code = int(self.srs_param.split(":")[-1])  # get the last element of the ':' splitted string
            elif key == "WIDTH":
                self.width_param = val
            elif key == "HEIGHT":
                self.height_param = val
            elif key == "FILTER":
                self.filter_param = val
            elif key == "TYPENAME":
                self.type_name_param = val

        if self.request_param.upper() == ServiceOperationEnum.GET_FEATURE.value.upper() and self.type_name_param is not None:
            # for WFS we need to check a few things in here!
            # first get the featuretype object, that is requested
            featuretype = FeatureType.objects.get(
                metadata__identifier=self.type_name_param,
                service__metadata=metadata
            )

            if self.srs_param is None:
                # if the srs_param could not be identified by a GET parameter, we need to check if the default srs of the
                # featuretype object is set. Otherwise we take our DEFAULT_STRING constant (EPSG:4326)
                if featuretype.default_srs is None:
                    self.srs_param = DEFAULT_SRS_STRING
                    self.srs_code = DEFAULT_SRS
                else:
                    self.srs_param = "EPSG:{}".format(featuretype.default_srs.code)
                    self.srs_code = int(featuretype.default_srs.code)

                try:
                    tmp = []
                    # Since the OGC standard does not specify a single identifier for the geometry part in a featuretype,
                    # we need to check if our featuretype holds ANYTHING that matches the possible geometry identifiers...
                    for allowed_geom_id in ALLLOWED_FEATURE_TYPE_ELEMENT_GEOMETRY_IDENTIFIERS:
                        elements = featuretype.elements.filter(
                            type__contains=allowed_geom_id
                        )
                        tmp += list(elements)
                    if len(tmp) > 0:
                        self.geom_property_name = tmp[0].name
                except ObjectDoesNotExist:
                    pass

        self._process_bbox_param()
        self._process_x_y_param()
        self._process_transaction_geometries()

    def _parse_POST_xml_body(self, body: bytes):
        """ Reads all relevant request data from the POST body xml document

        For development the following (only available) example of a WMS GetMap request as xml document was used:
        https://docs.geoserver.org/stable/en/user/services/wms/reference.html

        Furthermore for the WFS operation implementation the following Oracle documentation was used:
        https://docs.oracle.com/database/121/SPATL/wfs-operations-requests-and-responses-xml-examples.htm#SPATL926

        Args:
            body (bytes): The POST body as bytes
        Returns:

        """
        body = body.decode("UTF-8")
        xml = xml_helper.parse_xml(body)
        self.POST_raw_body = body

        root = xml_helper.try_get_single_element_from_xml(elem="/*", xml_elem=xml)
        self.request_param = QName(root).localname
        self.version_param = xml_helper.try_get_attribute_from_xml_element(root, "version")

        self.layer_param = xml_helper.try_get_text_from_xml_element(xml, "//" + GENERIC_NAMESPACE_TEMPLATE.format("NamedLayer") + "/" + GENERIC_NAMESPACE_TEMPLATE.format("Name"))

        bbox_elem = xml_helper.try_get_single_element_from_xml(elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("BoundingBox"), xml_elem=xml)

        self.srs_param = xml_helper.try_get_attribute_from_xml_element(bbox_elem, "srsName")

        bbox_extent = []
        bbox_coords = xml_helper.try_get_element_from_xml(elem=".//" + GENERIC_NAMESPACE_TEMPLATE.format("coord"), xml_elem=bbox_elem)

        tmp = ["X", "Y"]
        for coord in bbox_coords:
            for t in tmp:
                bbox_extent.append(xml_helper.try_get_text_from_xml_element(elem="./" + GENERIC_NAMESPACE_TEMPLATE.format(t), xml_elem=coord))

        self.bbox_param = ",".join(bbox_extent)

        output_elem = xml_helper.try_get_single_element_from_xml(elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("Output"), xml_elem=xml)
        self.format_param = xml_helper.try_get_text_from_xml_element(output_elem, "./" + GENERIC_NAMESPACE_TEMPLATE.format("Format"))

        size_elem = xml_helper.try_get_single_element_from_xml(elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("Size"), xml_elem=output_elem)
        self.height_param = int(xml_helper.try_get_text_from_xml_element(size_elem, "./" + GENERIC_NAMESPACE_TEMPLATE.format("Height")))
        self.width_param = int(xml_helper.try_get_text_from_xml_element(size_elem, "./" + GENERIC_NAMESPACE_TEMPLATE.format("Width")))

        # type_name differs in WFS versions
        if self.version_param == VersionEnum.V_2_0_2.value or self.version_param == VersionEnum.V_2_0_0.value:
            type_name = "typeNames"
        else:
            type_name = "typeName"

        self.type_name_param = xml_helper.try_get_attribute_from_xml_element(xml, type_name, "//" + GENERIC_NAMESPACE_TEMPLATE.format("Query"))
        self.filter_param = xml_helper.xml_to_string(xml_helper.try_get_single_element_from_xml(elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("Filter"), xml_elem=xml))

    def _get_geom_filter_param(self, as_snippet: bool = False):
        """ Creates a xml string for the filter parameter of a WFS operation

        Returns:
             _filter (str): The xml parameter as string
        """
        _filter = ""
        _filter_prefix = ""
        nsmap = {"gml": XML_NAMESPACES["gml"]}
        gml = "{" + nsmap.get("gml") + "}"

        if self.version_param == "1.0.0" or self.version_param == "1.1.0":
            # default implementation, nothing to do here
            pass

        elif self.version_param == "2.0.0" or self.version_param == "2.0.2":
            nsmap["fes"] = XML_NAMESPACES["fes"]
            _filter_prefix = "{" + nsmap.get("fes") + "}"

        # create xml filter string
        root = etree.Element("{}Filter".format(_filter_prefix), nsmap=nsmap)
        within_elem = xml_helper.create_subelement(root, "{}Within".format(_filter_prefix))
        property_elem = xml_helper.create_subelement(within_elem, "{}PropertyName".format(_filter_prefix))
        property_elem.text = self.geom_property_name
        polygon_elem = xml_helper.create_subelement(within_elem, "{}Polygon".format(gml),
                                                    attrib={"srsName": self.srs_param})
        outer_bound_elem = xml_helper.create_subelement(polygon_elem, "{}outerBoundaryIs".format(gml))
        linear_ring_elem = xml_helper.create_subelement(outer_bound_elem, "{}LinearRing".format(gml))
        pos_list_elem = xml_helper.create_subelement(linear_ring_elem, "{}posList".format(gml))
        tmp = []

        for vertex in self.intersected_allowed_geometry.convex_hull.coords[0]:
            tmp.append(str(vertex[0]))
            tmp.append(str(vertex[1]))
        pos_list_elem.text = " ".join(tmp)

        if as_snippet:
            # we do not need the root <Filter> element, so just take the <Within> element and below!
            root = xml_helper.try_get_element_from_xml("//" + GENERIC_NAMESPACE_TEMPLATE.format("Within"), root)

        _filter = xml_helper.xml_to_string(root)

        return _filter

    def set_intersected_allowed_geometry(self, allowed_geom: GEOSGeometry):
        """ Setter for the intersected_allowed_geometry

        Removes data for the bbox_param and changes the geometry filter

        Args:
            allowed_geom (GEOSGeometry): The intersected, allowed geometry
        Returns:
        """
        self.intersected_allowed_geometry = allowed_geom
        uri_parsed = urllib.parse.urlparse(self.uri)
        query = dict(urllib.parse.parse_qsl(uri_parsed.query))

        # remove bbox parameter (also from uri)
        self.bbox_param = None
        try:
            del query["bbox"]
        except KeyError:
            # it was not there in the first place
            pass
        try:
            del self.new_params_dict["BBOX"]
        except KeyError:
            # it was not there in the first place
            pass

        # change filter param, so the allowed_geom is the bounding geometry
        # create complete new filter object
        _filter = self._get_geom_filter_param(as_snippet=False)
        query["filter"] = _filter
        self.filter_param = _filter
        self.new_params_dict["FILTER"] = _filter

        query = urllib.parse.urlencode(query, safe=", :")
        uri_parsed = uri_parsed._replace(query=query)
        self.uri = urllib.parse.urlunparse(uri_parsed)

    def get_bounding_geometry_from_filter_param(self):
        """ Returns the gml:lowerCorner/gml:upperCorner data as Geometry bounding box

        Returns:
        """
        bounding_geom = None
        if self.filter_param is None:
            return bounding_geom
        filter_xml = xml_helper.parse_xml(self.filter_param)

        # a simple bbox could be inside gml:Envelope/gml:lowerCorner and gml:Envelope/gml:upperCorner
        lower_corner = xml_helper.try_get_text_from_xml_element(filter_xml, "//" + GENERIC_NAMESPACE_TEMPLATE.format("lowerCorner"))
        upper_corner = xml_helper.try_get_text_from_xml_element(filter_xml, "//" + GENERIC_NAMESPACE_TEMPLATE.format("upperCorner"))

        gml_polygons = xml_helper.try_get_element_from_xml("//" + GENERIC_NAMESPACE_TEMPLATE.format("Polygon"), filter_xml)

        if lower_corner is not None and upper_corner is not None:
            # there is a simple bbox
            lower_corner = lower_corner.split(" ")
            upper_corner = upper_corner.split(" ")
            corners = lower_corner + upper_corner
            bounding_geom = GEOSGeometry(Polygon.from_bbox(corners), srid=self.srs_code or DEFAULT_SRS)
        elif len(gml_polygons) > 0:
            # there are n polygons
            geom_collection = GeometryCollection(srid=self.srs_code or DEFAULT_SRS)
            for polygon in gml_polygons:
                vertices = xml_helper.try_get_text_from_xml_element(polygon, ".//" + GENERIC_NAMESPACE_TEMPLATE.format("posList")).split(" ")
                vertices_pairs = []
                for i in range(0, len(vertices), 2):
                    vertices_pairs.append((float(vertices[i]), float(vertices[i+1])))
                polygon_obj = GEOSGeometry(
                    Polygon(
                        vertices_pairs
                    ),
                    srid=self.srs_code or DEFAULT_SRS
                )
                geom_collection.append(polygon_obj)
            bounding_geom = geom_collection.unary_union

        return bounding_geom

    def _process_bbox_param(self):
        """ Creates a polygon from the given string bounding box

        Args:

        Returns:
            Nothing, performs method directly on object
        """
        ret_dict = {
            "geom": None,
            "bbox_param": None
        }
        if self.bbox_param is None:
            return ret_dict
        # epsg_api = EpsgApi()

        # create Polygon object from raw BBOX parameter
        tmp_bbox = self.bbox_param.split(",")

        if len(tmp_bbox) != 4:
            return HttpResponse(status=500, content=SECURITY_PROXY_ERROR_PARAMETER.format("BBOX"))
        bbox_param_geom = GEOSGeometry(Polygon.from_bbox(tmp_bbox), srid=self.srs_code)

        # check whether the axis of the bbox extent vertices have to be switched
        # switch_axis = epsg_api.switch_axis_order(service_type, srs_param)

        # if switch_axis:
        #    for i in range(0, len(tmp_bbox)-1, 2):
        #        tmp = tmp_bbox[i]
        #        tmp_bbox[i] = tmp_bbox[i+1]
        #        tmp_bbox[i+1] = tmp

        ret_dict["geom"] = bbox_param_geom
        ret_dict["bbox_param"] = ",".join(tmp_bbox)

        self.new_params_dict["BBOX"] = ret_dict["bbox_param"]
        self.bbox_param = ret_dict

    def _process_x_y_param(self):
        """ Creates a point from the given x_y_param dict

        Args:

        Returns:
            Nothing, performs method directly on object

        """
        # create Point object from raw X/Y parameters
        if self.x_y_param[0] is None and self.x_y_param[1] is not None:
            # make sure both values are set or none
            return HttpResponse(status=500, content=SECURITY_PROXY_ERROR_PARAMETER.format("X"))
        elif self.x_y_param[0] is not None and self.x_y_param[1] is None:
            # make sure both values are set or none
            return HttpResponse(status=500, content=SECURITY_PROXY_ERROR_PARAMETER.format("Y"))
        elif self.x_y_param[0] is not None and self.x_y_param[1] is not None:
            # we can create a Point object from this!
            self.x_y_param = Point(int(self.x_y_param[0]), int(self.x_y_param[1]))
        else:
            self.x_y_param = None

        if self.x_y_param is not None:
            self.x_y_param = self._convert_image_point_to_spatial_coordinates(
                self.x_y_param,
                int(self.width_param),
                int(self.height_param),
                self.bbox_param.get("geom")[0],
            )

    def _process_transaction_geometries(self):
        """ Creates geometries from <gml:polygon> elements inside the transaction xml body

        Returns:
             nothing
        """
        # skip this if we have no transaction body
        if self.POST_raw_body is None:
            return

        xml_body = xml_helper.parse_xml(self.POST_raw_body)

        actions = ["INSERT", "UPDATE"]
        geom_collection = GeometryCollection()

        # Find INSERT and UPDATE geometries
        for action in actions:
            xml_elements = xml_helper.try_get_element_from_xml("//" + GENERIC_NAMESPACE_TEMPLATE.format(action), xml_body)

            for xml_element in xml_elements:
                polygon_elements = xml_helper.try_get_element_from_xml(".//" + GENERIC_NAMESPACE_TEMPLATE.format("Polygon"), xml_element)

                for poly in polygon_elements:
                    pos_list = xml_helper.try_get_text_from_xml_element(poly, ".//" + GENERIC_NAMESPACE_TEMPLATE.format("posList"))

                    if pos_list is None or len(pos_list) == 0:
                        continue

                    pos_list = pos_list.split(" ")
                    vertices_pairs = []

                    for i in range(0, len(pos_list), 2):
                        vertices_pairs.append((float(pos_list[i]), float(pos_list[i + 1])))

                    polygon_obj = GEOSGeometry(
                        Polygon(
                            vertices_pairs
                        ),
                        srid=self.srs_code or DEFAULT_SRS
                    )
                    geom_collection.append(polygon_obj)
        geom_collection = geom_collection.unary_union
        self.transaction_geometries = geom_collection

    def _convert_image_point_to_spatial_coordinates(self, point: Point, width: int, height: int, bbox_coords: list):
        """ Converts the x|y coordinates of an image point to spatial EPSG:4326 coordinates, derived from a bounding box

        Args:
            point (Point): The Point object, which holds the image x|y position
            width (int); The width of the image
            height (int); The height of the image
            bbox_coords (list); The bounding box vertices as tuples in a list
        Returns:
             point (Point): The Point object, holding converted spatial coordinates
        """

        # the coordinate systems origin is 0|0 in the upper left corner of the image
        # get the vertices of the bbox which represent these image points: 0|0, max|0, 0|max
        bbox_upper_left = bbox_coords[1]
        bbox_upper_right = bbox_coords[2]
        bbox_lower_left = bbox_coords[0]

        # calculate the movement vector (only the non-zero part)
        # divide the movement vector using the width/height to get a vector step size
        step_left_right = (bbox_upper_right[0] - bbox_upper_left[0]) / width
        step_up_down = (bbox_lower_left[1] - bbox_upper_left[1]) / height

        # x represents the upper left "corner", increased by the product of the image X coordinate and the step size for this direction
        # equivalent for y
        point.x = bbox_upper_left[0] + point.x * step_left_right
        point.y = bbox_upper_left[1] + point.y * step_up_down
        point.srid = self.srs_code
        return point

    def get_post_data_dict(self):
        """ Getter for the data which is used in a POST request

        Returns:
             post_data (dict)
        """
        post_data = self.new_params_dict
        return post_data

    def get_post_data_body(self):
        """ Getter for the data which is used in a POST request

        Returns:
             post_data (bytes)
        """
        ret_val = self.POST_raw_body
        if not isinstance(ret_val, bytes):
            ret_val = ret_val.encode("utf-8")
        return ret_val

    def get_operation_response(self, uri: str = None, post_data: dict = None):
        """ Fetching method for security proxy.

        Args:
            uri (str): The operation uri
        Returns:
             The xml response
        """
        if uri is None:
            uri = self.uri

        if post_data is None:
            post_data = self.get_post_data_dict()  # get default POST as dict content

        c = CommonConnector(url=uri)

        if self.request_is_GET:
            c.load()

        else:
            c.post(post_data)

        if c.status_code is not None and c.status_code != 200:
            raise Exception(c.status_code)

        return c.content

    def _check_get_feature_info_operation_access(self, sec_ops: QueryDict):
        """ Checks whether the user given x/y Point parameter object is inside the geometry, which defines the allowed
        access for the GetFeatureInfo operation

        Args:
            sec_ops (QueryDict): A QueryDict containing SecuredOperation objects
        Returns:
             Whether the Point is inside the geometry or not
        """

        # User is at least in one group that has access to this operation on this metadata.
        # Now check the spatial restriction!
        constraints = {}
        if self.x_y_param is not None:
            constraints["x_y"] = False

        for sec_op in sec_ops:
            if sec_op.bounding_geometry.empty:
                # there is no specific area, so this group is allowed to request everywhere
                constraints["x_y"] = True
                break
            total_bounding_geometry = sec_op.bounding_geometry.unary_union
            if self.x_y_param is not None:
                if total_bounding_geometry.covers(self.x_y_param):
                    constraints["x_y"] = True

        return False not in constraints.values()

    def _get_secured_service_mask(self, metadata: Metadata, sec_ops: QueryDict):
        """ Creates call to local mapserver and returns the response

        Gets a mask image, which can be used to remove restricted areas from another image

        Args:
            metadata (Metadata): The metadata object
            sec_ops (QueryDict): SecuredOperation objects in a query dict
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
                "srs": self.srs_param,
                "bbox": self.bbox_param.get("bbox_param"),
                "width": self.width_param,
                "height": self.height_param,
                "keys": op.id,
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
            response = c.content

        return response

    def _create_masked_image(self, img: bytes, mask: bytes, as_bytes: bool = False):
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

    def _check_get_feature_operation_access(self, sec_ops: QueryDict):
        """ Checks whether the GetFeature request can be allowed or not.

        Checks the SecuredOperations against bounding geometry from the request

        Args:
            sec_ops (QueryDict): The SecuredOperations in a QueryDict object
        Returns:
             True|False
        """
        ret_val = False

        # GetFeature operation is a WFS operation, which means the given bbox parameter must not be in EPSG:4326!
        bounding_geom = self.bbox_param

        if bounding_geom is None:
            # check if the filter parameter holds a bbox OR a bounding polygon
            bounding_geom = self.get_bounding_geometry_from_filter_param()
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
                self.set_intersected_allowed_geometry(bounding_geom.intersection(access_restricting_geom))
                ret_val = True

        return ret_val

    def _check_transaction_operation_access(self, sec_ops: QueryDict):
        """ Checks whether the Transaction request can be allowed or not.

        Checks the SecuredOperations against geometries from the request

        Args:
            sec_ops (QueryDict): The SecuredOperations in a QueryDict object
        Returns:
             True|False
        """
        ret_val = True

        for sec_op in sec_ops:

            if sec_op.bounding_geometry.empty:
                # there is no allowed area defined, so this group is allowed to request everywhere
                return ret_val

            bounding_geom = sec_op.bounding_geometry.unary_union

            if not bounding_geom.covers(self.transaction_geometries):
                # If the geometries, that can be found in the transaction operation are not fully covered by the allowed
                # geometry, we do not allowe the access!
                return False

        return ret_val

    def get_secured_operation_response(self, request: HttpRequest, metadata: Metadata):
        """ Calls the operation of a service if it is secured.

        Args:
            request (HttpRequest):
            metadata (Metadata):
        Returns:

        """
        # get use from request
        user = user_helper.get_user(request=request)
        response = None

        # if user could not be found in request -> not logged in -> no permission!
        if user is None:
            return response

        # check if the metadata allows operation performing for certain groups
        sec_ops = metadata.secured_operations.filter(
            operation__operation_name__iexact=self.request_param,
            allowed_group__in=user.groups.all(),
        )

        if sec_ops.count() == 0:
            # this means the service is secured but the no groups have access!
            return response

        else:

            # WMS - Features
            if self.request_param.upper() == ServiceOperationEnum.GET_FEATURE_INFO.value.upper():
                allowed = self._check_get_feature_info_operation_access(sec_ops)
                if allowed:
                    response = self.get_operation_response()

            # WMS - 'Map image'
            elif self.request_param.upper() == ServiceOperationEnum.GET_MAP.value.upper():
                # no need to check if the access is allowed, since we mask the output anyway
                img = self.get_operation_response()
                mask = self._get_secured_service_mask(metadata, sec_ops)
                response = self._create_masked_image(img, mask, as_bytes=True)

            # WFS
            elif self.request_param.upper() == ServiceOperationEnum.GET_FEATURE.value.upper():
                allowed = self._check_get_feature_operation_access(sec_ops)
                if allowed:
                    response = self.get_operation_response()

            # WFS
            elif self.request_param.upper() == ServiceOperationEnum.TRANSACTION.value.upper():
                allowed = self._check_transaction_operation_access(sec_ops)
                if allowed:
                    response = self.get_operation_response(self.POST_raw_body)

            return response