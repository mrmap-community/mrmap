"""Convert a WFS 2.0 GML 3.2 GetFeature response into the normalized feature collection.

The collection is the one the live preview and the map viewer consume, so a service that only
advertises GML needs neither a browser side XML reader nor a second converter. The supported
document subset is narrow on purpose and everything outside it is answered with its own state:

* the root is ``wfs:FeatureCollection`` and every member is ``wfs:member`` holding exactly one
  feature element; its identifier comes from ``gml:id`` or ``fid``.
* the geometry property is the one named by the stored ``FeatureType`` schema, falling back to the
  single GML geometry property of the member. Supported geometries are ``Point``, ``LineString``,
  ``Polygon``, ``Surface`` encoded as ``PolygonPatch``, the matching ``MultiPoint``,
  ``MultiLineString``, ``MultiCurve``, ``MultiSurface``, ``MultiPolygon`` and ``MultiGeometry``.
  Anything else, a ``Solid``, a ``CompositeSurface``, a curve segment or an ``Envelope`` used as
  feature geometry, is refused instead of approximated.
* coordinates come from ``gml:pos`` and ``gml:posList`` only. The deprecated ``gml:coordinates``
  encoding is refused because its value pairs do not state the axis order they follow.
* ``srsName`` must state the geographic CRS the request asked for, in either axis order; a
  projected or otherwise foreign CRS is refused instead of reprojected. ``srsDimension`` must be
  absent or ``2``, so heights are never dropped in silence.
* a property whose content is a nested element, or a feature or geometry that is only an
  ``xlink:href`` into another document, is a complex application schema and is refused. Remote
  references are never read.

Output geometry coordinates are longitude/latitude, like the GeoJSON the same contract carries.
"""
import math

from lxml import etree

GML = "http://www.opengis.net/gml/3.2"
XLINK = "http://www.w3.org/1999/xlink"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
# The request asks for one geographic CRS; both of its axis orders are accepted, because gml:pos
# follows the axis order of the CRS its element names.
LATITUDE_FIRST = ("EPSG:4326", "URN:OGC:DEF:CRS:EPSG::4326", "HTTP://WWW.OPENGIS.NET/DEF/CRS/EPSG/0/4326")
LONGITUDE_FIRST = ("CRS:84", "URN:OGC:DEF:CRS:OGC::CRS84", "URN:OGC:DEF:CRS:OGC:1.3:CRS84",
                   "HTTP://WWW.OPENGIS.NET/DEF/CRS/OGC/1.3/CRS84")
POINT, LINE_STRING, LINEAR_RING, POLYGON, SURFACE = "Point", "LineString", "LinearRing", "Polygon", "Surface"
# GML aggregate -> the member elements it holds, the geometry they wrap and the GeoJSON type.
AGGREGATES = {
    "MultiPoint": (("pointMember", "pointProperty"), POINT, "MultiPoint"),
    "MultiLineString": (("lineStringMember", "lineStringProperty"), LINE_STRING, "MultiLineString"),
    "MultiCurve": (("curveMember",), LINE_STRING, "MultiLineString"),
    "MultiSurface": (("surfaceMember",), SURFACE, "MultiPolygon"),
    "MultiPolygon": (("polygonMember",), POLYGON, "MultiPolygon"),
}
GEOMETRY_COLLECTION = "MultiGeometry"
GEOMETRIES = {POINT, LINE_STRING, LINEAR_RING, POLYGON, SURFACE, GEOMETRY_COLLECTION} | set(AGGREGATES)
# The nil statement of a property or a geometry: gml:nil in GML 3.2, xsi:nil in older encodings.
NIL_ATTRIBUTES = (f"{{{GML}}}nil", f"{{{XSI}}}nil")


class GmlError(Exception):
    """A document outside the supported subset, carrying the state the caller answers with."""

    def __init__(self, code, status=422):
        self.code = code
        self.status = status


def _name(element):
    return etree.QName(element).localname


def _is_nil(element):
    return any(element.get(attribute) in ("true", "1") for attribute in NIL_ATTRIBUTES)


def _elements(element):
    """The element children of an element, refusing any other kind of content.

    An entity reference the safe parser left unresolved stays in the tree as a node that is not an
    element, which is how a document that would make a reader reach outside itself shows up here.
    """
    children = [child for child in element if isinstance(child.tag, str)]
    if len(children) != len(list(element)):
        raise GmlError("gmlSchema")
    return children


def _offset(srs_name, requested):
    """Count the coordinates of a value that precede the longitude, refusing a foreign CRS."""
    name = (srs_name or requested or "").strip().upper()
    if name in LONGITUDE_FIRST:
        return 0
    if name in LATITUDE_FIRST:
        return 1
    raise GmlError("crs")


def _dimension(element):
    value = element.get("srsDimension") or element.get("dimension")
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        raise GmlError("gmlSchema")


def _positions(element, dimension, offset):
    """Read the coordinates of one geometric primitive, longitude first."""
    children = _elements(element)
    if len(children) != 1 or _name(children[0]) not in ("pos", "posList"):
        # gml:coordinates and gml:coord are the deprecated encodings, any other content is a
        # nested schema; both are refused instead of being guessed.
        raise GmlError("gmlSchema")
    child = children[0]
    values = child.text.split() if child.text else []
    declared = dimension if dimension is not None else _dimension(child)
    if declared is None and _name(child) == "pos":
        # A single position states its own dimension by its value count.
        declared = len(values)
    if declared not in (None, 2):
        raise GmlError("gmlDimension")
    if len(values) % 2 != 0:
        raise GmlError("malformed")
    positions = []
    for start in range(0, len(values), 2):
        longitude, latitude = float(values[start + offset]), float(values[start + 1 - offset])
        positions.append([longitude, latitude])
    if not positions or not all(math.isfinite(value) for position in positions for value in position):
        raise GmlError("malformed")
    return positions


def _is_gml_geometry(element):
    return _name(element) in GEOMETRIES and element.nsmap.get(element.prefix) == GML


def _is_geometry_property(property_element):
    """True for the property element holding exactly one GML geometry of the supported subset."""
    if _is_nil(property_element) or property_element.get(f"{{{XLINK}}}href") is not None:
        return False
    children = _elements(property_element)
    return len(children) == 1 and _is_gml_geometry(children[0])


def _rings(element, dimension, offset, name):
    """Read the exterior and interior rings of a GML Polygon or of a Surface PolygonPatch."""
    if name == SURFACE:
        patches = [child for child in _elements(element) if _name(child) == "patches"]
        if len(patches) != 1:
            raise GmlError("gmlSchema")
        polygons = [child for child in _elements(patches[0]) if _name(child) == "PolygonPatch"]
        if len(polygons) != 1:
            raise GmlError("gmlSchema")
        element = polygons[0]
    rings = _elements(element)
    if not rings or _name(rings[0]) != "exterior" or any(
            _name(ring) not in ("exterior", "interior") for ring in rings):
        raise GmlError("gmlSchema")
    coordinates = []
    for ring in rings:
        linear_rings = [child for child in _elements(ring) if _name(child) == LINEAR_RING]
        if len(linear_rings) != 1:
            raise GmlError("gmlSchema")
        positions = _positions(linear_rings[0], dimension, offset)
        if len(positions) < 4:
            raise GmlError("gmlSchema")
        if positions[0] != positions[-1]:
            # GML states a ring closes itself; a server that omits the repeated position still
            # means the closed ring, and the normalized collection requires it.
            positions.append(list(positions[0]))
        coordinates.append(positions)
    return coordinates


def _aggregate(element, name, srs_name, requested):
    """Convert one GML aggregate into the GeoJSON multi geometry it maps to."""
    member_names, wrapped, geojson_type = AGGREGATES[name]
    expected = {POINT: POINT, LINE_STRING: LINE_STRING}.get(wrapped, POLYGON)
    members = []
    for member in _elements(element):
        if _name(member) not in member_names:
            raise GmlError("gmlSchema")
        children = _elements(member)
        if len(children) != 1:
            raise GmlError("gmlSchema")
        geometry = _geometry(children[0], srs_name, requested)
        if geometry["type"] != expected:
            raise GmlError("gmlSchema")
        members.append(geometry)
    if not members:
        raise GmlError("gmlSchema")
    if geojson_type in ("MultiPoint", "MultiLineString"):
        return {"type": geojson_type, "coordinates": [member["coordinates"] for member in members]}
    coordinates = []
    for member in members:
        # Every member polygon is one polygon of the multi polygon, with all of its rings.
        coordinates.append(member["coordinates"])
    return {"type": "MultiPolygon", "coordinates": coordinates}


def _collection(element, srs_name, requested):
    """Convert a GML MultiGeometry, whose members may hold any supported geometry."""
    geometries = []
    for child in _elements(element):
        if _name(child) in ("geometryMember", "geometryAsFollows"):
            members = _elements(child)
            if len(members) != 1:
                raise GmlError("gmlSchema")
            geometries.append(_geometry(members[0], srs_name, requested))
        elif _is_gml_geometry(child):
            geometries.append(_geometry(child, srs_name, requested))
        else:
            raise GmlError("gmlSchema")
    if not geometries:
        raise GmlError("gmlSchema")
    return {"type": "GeometryCollection", "geometries": geometries}


def _geometry(element, srs_name, requested):
    """Convert one GML 3.2 geometry element into a longitude first GeoJSON geometry."""
    if not _is_gml_geometry(element):
        raise GmlError("gmlSchema")
    if element.get(f"{{{XLINK}}}href") is not None:
        raise GmlError("gmlRemote")
    if _is_nil(element):
        raise GmlError("gmlSchema")
    name = _name(element)
    offset = _offset(element.get("srsName") or srs_name, requested)
    dimension = _dimension(element)
    if name == POINT:
        positions = _positions(element, dimension, offset)
        if len(positions) != 1:
            raise GmlError("gmlSchema")
        return {"type": "Point", "coordinates": positions[0]}
    if name in (LINE_STRING, LINEAR_RING):
        positions = _positions(element, dimension, offset)
        if len(positions) < 2:
            raise GmlError("gmlSchema")
        return {"type": "LineString", "coordinates": positions}
    if name in (POLYGON, SURFACE):
        return {"type": "Polygon", "coordinates": _rings(element, dimension, offset, name)}
    if name in AGGREGATES:
        return _aggregate(element, name, srs_name, requested)
    return _collection(element, srs_name, requested)


def _value(property_element):
    """Read a simple feature property value; nested content is a complex application schema."""
    if _is_nil(property_element):
        return None
    if _elements(property_element):
        raise GmlError("gmlSchema")
    return property_element.text.strip() \
        if property_element.text and property_element.text.strip() else None


def _resolve_geometry(properties, stored_name):
    """Pick the geometry property, using the stored schema name to break qualified ties."""
    candidates = [item for item in properties if _is_geometry_property(item)]
    if not candidates and stored_name:
        # A null value of the property the stored schema names is still the geometry property.
        candidates = [item for item in properties
                      if _name(item) == stored_name.split(":")[-1] and _is_nil(item)]
    if not candidates:
        return None
    if stored_name:
        preferred = [item for item in candidates if _name(item) == stored_name.split(":")[-1]]
        candidates = preferred or candidates
    if len(candidates) > 1:
        # A simple feature has exactly one geometry property; more than one is a schema the
        # renderer cannot decide between.
        raise GmlError("gmlSchema")
    return candidates[0]


def _feature(member, stored_geometry_property, requested):
    """Convert one wfs:member into a GeoJSON feature with its stable identifier."""
    elements = _elements(member)
    if len(elements) != 1:
        raise GmlError("gmlSchema")
    element = elements[0]
    properties = _elements(element)
    if any(item.get(f"{{{XLINK}}}href") is not None for item in [element] + properties):
        # A feature or property that only points into another document is never read.
        raise GmlError("gmlRemote")
    geometry_property = _resolve_geometry(properties, stored_geometry_property)
    geometry = None
    if geometry_property is not None and not _is_nil(geometry_property):
        geometry = _geometry(_elements(geometry_property)[0], element.get("srsName"), requested)
    feature = {"type": "Feature", "geometry": geometry, "properties": {}}
    identifier = element.get(f"{{{GML}}}id") or element.get("fid")
    if identifier:
        feature["id"] = identifier
    for property_element in properties:
        if property_element is geometry_property or _is_geometry_property(property_element):
            # A feature may carry more than one geometric property, e.g. a generalised geometry.
            # The normalized contract has one geometry channel, so the one the stored schema
            # selects is rendered and the remaining geometric properties are left out.
            continue
        feature["properties"][_name(property_element)] = _value(property_element)
    return feature


def feature_collection(root, limit, stored_geometry_property=None, requested_crs="EPSG:4326"):
    """Convert a parsed WFS 2.0 GetFeature response into the normalized feature collection.

    ``stored_geometry_property`` is the geometry property name the registry knows from the stored
    DescribeFeatureType schema; it only breaks ties between qualified properties and is never
    written back. Permissions, spatial restrictions and coordinate validation stay with the
    caller, exactly as they are for a GeoJSON answer.
    """
    if _name(root) != "FeatureCollection":
        raise GmlError("format")
    if any(_name(member) not in ("member", "boundedBy") for member in _elements(root)):
        raise GmlError("format")
    members = [member for member in _elements(root) if _name(member) == "member"]
    if len(members) > limit:
        raise GmlError("limit", 502)
    return {"type": "FeatureCollection",
            "features": [_feature(member, stored_geometry_property, requested_crs)
                         for member in members]}
