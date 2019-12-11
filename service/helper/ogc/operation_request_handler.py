"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 05.12.19

"""
import urllib

from django.core.exceptions import ObjectDoesNotExist
from lxml import etree

from django.contrib.gis.geos import Polygon, GEOSGeometry, Point, GeometryCollection
from django.http import HttpRequest, HttpResponse

from MapSkinner.messages import SECURITY_PROXY_ERROR_PARAMETER
from MapSkinner.settings import GENERIC_NAMESPACE_TEMPLATE, XML_NAMESPACES
from service.helper import xml_helper
from service.models import Metadata, FeatureType
from service.settings import ALLLOWED_FEATURE_TYPE_ELEMENT_GEOMETRY_IDENTIFIERS, DEFAULT_SRS, DEFAULT_SRS_STRING


class OperationRequestHandler:
    """ Provides methods for handling an operation request for OGC services

    """

    def __init__(self, uri: str, request: HttpRequest, metadata: Metadata):
        self.uri = uri

        self.request_param = None  # refers to param 'REQUEST'
        self.layer_param = None  # refers to param 'LAYERS'
        self.x_y_param = [None, None]  # refers to param 'X/Y' (WMS 1.0.0), 'X, Y' (WMS 1.1.1), 'I,J' (WMS 1.3.0)
        self.bbox_param = None  # refers to param 'BBOX'
        self.srs_param = None  # refers to param 'SRS' (WMS 1.0.0 - 1.1.1) and 'CRS' (WMS 1.3.0)
        self.srs_code = None  # only the srsid as int
        self.version_param = None  # refers to param 'VERSION'
        self.filter_param = None  # refers to param 'FILTER' (WFS)
        self.width_param = None  # refers to param 'WIDTH' (WMS)
        self.height_param = None  # refers to param 'HEIGHT' (WMS)
        self.type_name_param = None  # refers to param 'TYPENAME' (WFS)
        self.geom_property_name = None  # will be set, if type_name_param is not None

        self.intersected_allowed_geometry = None

        for key, val in request.GET.items():
            key = key.upper()
            if key == "REQUEST":
                self.request_param = val
            if key == "LAYER":
                self.layer_param = val
            if key == "BBOX":
                self.bbox_param = val
            if key == "X" or key == "I":
                self.x_y_param[0] = val
            if key == "Y" or key == "J":
                self.x_y_param[1] = val
            if key == "VERSION":
                self.version_param = val
            if key == "SRS" or key == "CRS":
                self.srs_param = val
                self.srs_code = int(self.srs_param.split(":")[-1])  # get the last element of the ':' splitted string
            if key == "WIDTH":
                self.width_param = val
            if key == "HEIGHT":
                self.height_param = val
            if key == "FILTER":
                self.filter_param = val
            if key == "TYPENAME":
                self.type_name_param = val

        if self.request_param == "GetFeature" and self.type_name_param is not None:
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

        self.process_bbox_param()
        self.process_x_y_param()

    def get_geom_filter_param(self):
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

        # change filter param, so the allowed_geom is the bounding geometry
        _filter = self.get_geom_filter_param()
        query["filter"] = _filter

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

    def process_bbox_param(self):
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

        self.bbox_param = ret_dict

    def process_x_y_param(self):
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
