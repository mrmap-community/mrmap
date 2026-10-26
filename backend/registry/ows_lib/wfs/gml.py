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

Django's ``GEOSGeometry.from_gml()`` parses the geometry through GDAL/GEOS. This module
retains only WFS feature extraction and the subset/axis-order checks required by the preview.
Output geometry coordinates are longitude/latitude, like the GeoJSON the same contract carries.
"""
import json
import math

from django.contrib.gis.gdal import GDALException
from django.contrib.gis.geos import GEOSException, GEOSGeometry

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
# GML aggregate -> its member elements and the geometry they wrap.
AGGREGATES = {
    "MultiPoint": (("pointMember", "pointProperty"), POINT),
    "MultiLineString": (("lineStringMember", "lineStringProperty"), LINE_STRING),
    "MultiCurve": (("curveMember",), LINE_STRING),
    "MultiSurface": (("surfaceMember",), SURFACE),
    "MultiPolygon": (("polygonMember",), POLYGON),
}
GEOMETRY_COLLECTION = "MultiGeometry"
GEOMETRIES = {POINT, LINE_STRING, LINEAR_RING, POLYGON, SURFACE, GEOMETRY_COLLECTION} | set(AGGREGATES)
# The nil statement of a property or a geometry: gml:nil in GML 3.2, xsi:nil in older encodings.
NIL_ATTRIBUTES = (f"{{{GML}}}nil", f"{{{XSI}}}nil")


# Only these local geometry elements reach GDAL. In particular no remote reference, entity,
# deprecated coordinate encoding or curved geometry can be resolved or approximated by it.
CHILDREN = {
    POINT: {"pos", "posList"}, LINE_STRING: {"pos", "posList"}, LINEAR_RING: {"pos", "posList"},
    POLYGON: {"exterior", "interior"}, SURFACE: {"patches"},
    "patches": {"PolygonPatch"}, "PolygonPatch": {"exterior", "interior"},
    "exterior": {LINEAR_RING}, "interior": {LINEAR_RING},
    GEOMETRY_COLLECTION: {"geometryMember", "geometryAsFollows"} | GEOMETRIES,
    "geometryMember": GEOMETRIES, "geometryAsFollows": GEOMETRIES,
}
for aggregate, (member_names, wrapped) in AGGREGATES.items():
    CHILDREN[aggregate] = set(member_names)
    for member_name in member_names:
        CHILDREN[member_name] = {wrapped} if wrapped in (POINT, LINE_STRING) else {POLYGON, SURFACE}


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


def _is_gml_geometry(element):
    return _name(element) in GEOMETRIES and element.nsmap.get(element.prefix) == GML


def _is_geometry_property(property_element):
    """True for the property element holding exactly one GML geometry of the supported subset."""
    if _is_nil(property_element) or property_element.get(f"{{{XLINK}}}href") is not None:
        return False
    children = _elements(property_element)
    return len(children) == 1 and _is_gml_geometry(children[0])


def _local_geometry(element, srs_name, requested, dimension=None):
    """Validate the preview subset and copy it to a self-contained, longitude first GML tree.

    GDAL reads coordinate tuples verbatim, regardless of srsName. It also accepts invalid numeric
    text as zero and can approximate curves. Keep these contract checks here; geometry parsing,
    polygon construction and aggregate conversion belong to GEOSGeometry.from_gml().
    Only approved elements/text are copied, so GDAL never receives upstream references or DTDs.
    """
    name = _name(element)
    if element.tag != f"{{{GML}}}{name}" or _is_nil(element):
        raise GmlError("gmlSchema")
    if element.get(f"{{{XLINK}}}href") is not None:
        raise GmlError("gmlRemote")
    srs_name = element.get("srsName") or srs_name
    offset = _offset(srs_name, requested)
    declared = _dimension(element)
    dimension = declared if declared is not None else dimension
    if dimension not in (None, 2):
        raise GmlError("gmlDimension")
    children = _elements(element)
    # GDAL expects the standard member wrappers rather than the legacy aliases we accept.
    local_name = {"pointProperty": "pointMember", "lineStringProperty": "lineStringMember",
                  "geometryAsFollows": "geometryMember"}.get(name, name)
    local = etree.Element(f"{{{GML}}}{local_name}", nsmap={"gml": GML})
    if name in ("pos", "posList"):
        if children:
            raise GmlError("gmlSchema")
        values = element.text.split() if element.text else []
        if name == "pos" and len(values) != 2:
            raise GmlError("gmlDimension")
        if not values or len(values) % 2:
            raise GmlError("malformed")
        try:
            values = [float(value) for value in values]
            if not all(math.isfinite(value) for value in values):
                raise ValueError
        except ValueError as error:
            raise GmlError("malformed") from error
        if offset:
            values = [value for pair in zip(values[1::2], values[::2]) for value in pair]
        local.text = " ".join(map(str, values))
        return local
    allowed = CHILDREN.get(name, set())
    if not children or any(_name(child) not in allowed for child in children):
        raise GmlError("gmlSchema")
    if (name in (POINT, LINE_STRING, LINEAR_RING, SURFACE, "patches", "exterior", "interior",
                 "geometryAsFollows") or name.endswith(("Member", "Property"))):
        if len(children) != 1:
            raise GmlError("gmlSchema")
    if name in (POLYGON, "PolygonPatch") and (
            _name(children[0]) != "exterior" or sum(_name(child) == "exterior" for child in children) != 1):
        raise GmlError("gmlSchema")
    local.extend(_local_geometry(child, srs_name, requested, dimension) for child in children)
    if name == POINT and len(local[0].text.split()) != 2:
        raise GmlError("gmlSchema")
    if name == GEOMETRY_COLLECTION:
        for child in list(local):
            if _name(child) in GEOMETRIES:
                wrapper = etree.Element(f"{{{GML}}}geometryMember")
                local.replace(child, wrapper)
                wrapper.append(child)
    if name == LINEAR_RING:
        # Preserve the preview's tolerance of a missing closing position before GEOS reads it.
        positions = local[0].text.split()
        if len(positions) < 8:
            raise GmlError("gmlSchema")
        if list(map(float, positions[:2])) != list(map(float, positions[-2:])):
            local[0].text += " " + " ".join(positions[:2])
    return local


def _geometry(element, srs_name, requested):
    """Delegate GML geometry parsing and GeoJSON construction to Django's GDAL/GEOS bridge."""
    local = _local_geometry(element, srs_name, requested)
    for ring in local.iter(f"{{{GML}}}LinearRing"):
        if ring.getparent() is None or _name(ring.getparent()) not in ("exterior", "interior"):
            # Rings outside polygon boundaries were exposed as lines by the response contract.
            ring.tag = f"{{{GML}}}LineString"
    try:
        geometry = GEOSGeometry.from_gml(etree.tostring(local, encoding="unicode"))
        if geometry.empty:
            raise GmlError("gmlSchema")
        return json.loads(geometry.json)
    except (GDALException, GEOSException, ValueError) as error:
        raise GmlError("gmlSchema") from error


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
