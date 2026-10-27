"""Capabilities documents which advertise exactly one registered resource.

A viewer which shall show exactly one layer or one feature type of a registered
service would otherwise get the document of the whole service and had to switch
everything else off by itself. This module narrows such a document down to the
requested resource.

The document which is narrowed down is never the stored one: it is generated out
of the registry (``registry/models/document.py``) by
:meth:`registry.models.service.Service.get_capabilitites_for_request`, so it
already answers the current state of the service and - for a camouflaged service -
only addresses of this deployment. Therefore nothing is stored here and nothing
has to be refreshed: the next request answers the next state of the service.

Only the resource list is narrowed, the service metadata and the advertised
operations are kept. Everything a nested layer inherits from its parents (CRS,
bounding boxes, styles) is written into the layer itself and the parents are
removed: the narrowed document advertises the requested layer as a single
drawable layer and does not keep the containers of a whole service document.
"""
import logging
from copy import deepcopy

from lxml import etree
from rest_framework.reverse import reverse

logger = logging.getLogger(__name__)

# The document versions this module narrows down, spelled like the documents spell
# them. These are exactly the versions the mapper configs answer a document for
# (registry/mappers/configs), so a document of another version can not be generated
# out of the registry and is refused instead of being narrowed with the rules of a
# version which may structure it differently.
SUPPORTED_VERSIONS = {
    "WMS": ("1.1.1", "1.3.0"),
    "WFS": ("1.0.0", "1.1.0", "2.0.0", "2.0.2"),
}

# The reasons a document can not be narrowed down, answered by the proxy view with
# an exception report of the according OGC exception code.
NOT_SUPPORTED = "not_supported"
NO_SUCH_ELEMENT = "no_such_element"
AMBIGUOUS_ELEMENT = "ambiguous_element"
MALFORMED = "malformed"

WMS_CAPABILITIES_URL = "wms-layer-capabilities"
WFS_CAPABILITIES_URL = "wfs-featuretype-capabilities"

LAYER = "Layer"
FEATURE_TYPE = "FeatureType"
NAME = "Name"

# The requested resource is looked up by the text of its Name child element, like
# the whole service does it when it secures a request (registry/helper/preview.py).
# The selection must answer the resource itself and not its Name child: everything
# which is removed out of the document afterwards is removed relative to it.
ELEMENT_XPATH = {
    "WMS": f"//*[local-name()='{LAYER}'][*[local-name()='{NAME}']/text()=$identifier]",
    "WFS": f"//*[local-name()='{FEATURE_TYPE}'][*[local-name()='{NAME}']/text()=$identifier]",
}

# The parameter of an operation which lists the type names of a service, spelled
# like the versions of WFS which use it spell it.
WFS_TYPE_NAME_PARAMS = ("name", "typeName")

# The child elements of a WMS Layer which a nested layer takes over from its
# parents as far as it does not answer them of its own: these kinds exist once
# per layer, so a nested layer does not combine them over its whole ancestry,
# the nearest parent which answers the kind wins.
INHERIT_SINGLE = (
    "Title", "Abstract", "Language", "Country", "Region",
    "MinScale", "MaxScale", "MinScaleDenominator", "MaxScaleDenominator",
    "ScaleHint", "LatLonBoundingBox", "EX_GeographicBoundingBox",
)

# The child elements of a WMS Layer which a nested layer takes over in addition
# to its own: every value of a parent which the layer does not name of its own
# stays valid. These kinds are identified by a value which no layer names twice,
# like the coordinate reference system of an extent or the name of a style.
INHERIT_ADDITIONAL = (
    "CRS", "SRS", "Style", "Dimension", "Time", "KeywordList",
    "AuthorityURL", "Identifier", "MetadataURL", "AttributeList",
    "Extent", "BoundingBox",
)

# The attributes of a WMS Layer element which a nested layer inherits: the layer
# keeps its own answer and takes the nearest answer of its parents for the
# attributes it does not name itself.
INHERITED_ATTRIBUTES = ("queryable", "opaque", "cascaded")


class CapabilitiesError(Exception):
    """A capabilities document can not be narrowed down to the requested resource.

    Attributes:
        code (str): one of the reasons above, to choose the exception report.
        status (int): the http status the answer of the endpoint should carry.
    """

    def __init__(self, code, message, status=502):
        super().__init__(message)
        self.code = code
        self.status = status


def _localname(element) -> str:
    """The tag of an element without the namespace it is written in."""
    tag = getattr(element, "tag", None)
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _children(element, name) -> list:
    """The direct children of an element with the given local name."""
    return [child for child in element if _localname(child) == name]


def _parse(document) -> etree._Element:
    """The root of a capabilities document which was asked for as bytes or string."""
    if isinstance(document, str):
        document = document.encode("utf-8")
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    try:
        root = etree.fromstring(document, parser=parser)
    except (etree.XMLSyntaxError, ValueError, TypeError):
        raise CapabilitiesError(
            MALFORMED,
            "The capabilities document of the service can not be read.",
            status=502,
        )
    if root is None:
        raise CapabilitiesError(
            MALFORMED,
            "The capabilities document of the service is empty.",
            status=502,
        )
    return root


def _requested_element(root, service_type, identifier):
    """The single element of the document which is named by the identifier.

    Raises:
        CapabilitiesError: if the document does not advertise the identifier exactly once.
    """
    found = root.xpath(ELEMENT_XPATH[service_type], identifier=identifier)
    if not found:
        raise CapabilitiesError(
            NO_SUCH_ELEMENT,
            "The capabilities document of the service does not advertise the "
            f"{LAYER if service_type == 'WMS' else FEATURE_TYPE} '{identifier}'.",
            status=404,
        )
    if len(found) > 1:
        raise CapabilitiesError(
            AMBIGUOUS_ELEMENT,
            "The capabilities document of the service advertises the identifier "
            f"'{identifier}' more than once.",
        )
    return found[0]


def _without_children(element):
    """Remove the elements nested in the requested element.

    A layer which is asked for as a single layer is advertised as a leaf: layers
    nested in it have names of their own and would be advertisable again.
    """
    for nested in _children(element, _localname(element)):
        element.remove(nested)


def _inheritance_key(element):
    """The value which identifies a child element of a WMS layer among the
    elements of the same kind which the layer inherits from its parents.

    None for the kinds which a layer either has of its own or takes from exactly
    one parent, because they do not exist twice in one layer.
    """
    name = _localname(element)
    if name == "Style":
        names = _children(element, NAME)
        return (names[0].text or "").strip() if names else None
    if name in ("CRS", "SRS"):
        return (element.text or "").strip()
    if name == "Identifier":
        return (element.get("code") or element.text or "").strip()
    if name == "MetadataURL":
        return element.get("type")
    if name in ("Extent", "BoundingBox"):
        return element.get("CRS") or element.get("crs")
    if name == "Time":
        return "time"
    # Dimension, AuthorityURL and AttributeList name themselves
    return element.get("name")


def _inherit_keywords(layer, keyword_list):
    """Add the keywords of a parent's keyword list to the layer's own."""
    own_lists = _children(layer, "KeywordList")
    if not own_lists:
        layer.append(deepcopy(keyword_list))
        return
    own_keywords = {
        (keyword.text or "").strip()
        for own_list in own_lists
        for keyword in _children(own_list, "Keyword")
    }
    for keyword in _children(keyword_list, "Keyword"):
        if (keyword.text or "").strip() not in own_keywords:
            own_lists[0].append(deepcopy(keyword))


def _inherit_from_parent(layer, parent):
    """Give the layer everything it inherits from one of its parents.

    The parents are answered from the inside outwards, so what a layer does not
    answer of its own keeps the value which the nearest parent gave it. The
    parents' own layers and names and the unknown extension elements of a
    document are not inherited.
    """
    for child in parent:
        name = _localname(child)
        if name == "KeywordList":
            _inherit_keywords(layer, child)
        elif name in INHERIT_SINGLE:
            if not _children(layer, name):
                layer.append(deepcopy(child))
        elif name in INHERIT_ADDITIONAL:
            own = _children(layer, name)
            key = _inheritance_key(child)
            if not any(key == _inheritance_key(own_element) for own_element in own):
                layer.append(deepcopy(child))
    for attribute in INHERITED_ATTRIBUTES:
        if layer.get(attribute) is None and parent.get(attribute) is not None:
            layer.set(attribute, parent.get(attribute))


def _without_parent_layers(element):
    """Remove the parents of a nested layer and write what it inherits into it.

    A layer which is advertised alone must stay drawable alone: everything it
    inherits from its parents, the coordinate reference systems, the bounding
    boxes and the styles, becomes part of the layer itself before the parents
    are removed. Therefore the parents, which in a document advertising a whole
    service are containers of inherited values, are not needed anymore and the
    document answers the layer as the only child of the capability.
    """
    parents = [ancestor for ancestor in element.iterancestors()
               if _localname(ancestor) == LAYER]
    if not parents:
        return
    for parent in parents:
        _inherit_from_parent(element, parent)
    outermost = parents[-1]
    container = outermost.getparent()
    container.insert(container.index(outermost), element)
    container.remove(outermost)


def _without_siblings(element):
    """Remove every branch of the tree the requested element is not nested in."""
    node = element
    parent = node.getparent()
    while parent is not None:
        for sibling in _children(parent, _localname(node)):
            if sibling is not node:
                parent.remove(sibling)
        node = parent
        parent = node.getparent()


def _without_other_type_names(root, identifier):
    """Restrict the type names an operation of a WFS advertises to one identifier.

    A parameter which does not constrain any value at all (`NoValues`) or which
    allows every value (`AnyValue`) names no type to narrow down and is kept as it
    is: rewriting it would advertise the requested type for an operation which
    offers none of them.
    """
    unconstrained = ("", "NoValues", "AnyValue")
    for parameter in root.iter():
        if _localname(parameter) != "Parameter":
            continue
        if parameter.get("name") not in WFS_TYPE_NAME_PARAMS:
            continue
        values = [value for value in parameter.iter() if _localname(value) == "Value"]
        if not values:
            continue
        if all((value.text or "").strip() in unconstrained for value in values):
            continue
        for value in values[1:]:
            value.getparent().remove(value)
        values[0].text = identifier


def single_resource(document, service_type, identifier) -> bytes:
    """The given capabilities document, narrowed down to one advertised resource.

    Args:
        document (bytes|str): the capabilities document of a service.
        service_type (str): "WMS" or "WFS", the type the document is written as.
        identifier (str): the identifier of the layer or feature type to advertise.

    Returns:
        bytes: the document, with the version and the namespaces of the given one,
        advertising only the requested resource.

    Raises:
        CapabilitiesError: if the document can not be narrowed down.
    """
    if not identifier:
        raise CapabilitiesError(
            NO_SUCH_ELEMENT,
            "The requested resource does not have an identifier to advertise.",
            status=404,
        )
    root = _parse(document)
    version = root.get("version")
    if version not in SUPPORTED_VERSIONS.get(service_type, ()):
        raise CapabilitiesError(
            NOT_SUPPORTED,
            f"MrMap does not narrow {service_type} capabilities documents of "
            f"version '{version}' down to a single resource.",
            status=501,
        )
    element = _requested_element(root, service_type, identifier)
    _without_children(element)
    if service_type == "WMS":
        _without_parent_layers(element)
    _without_siblings(element)
    if service_type == "WFS":
        _without_other_type_names(root, identifier)
    return etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", pretty_print=True
    )


def service_element_capabilities(service, element, request) -> bytes:
    """The capabilities of a registered service, narrowed down to one of its resources.

    The document is generated for this request out of the registry, so it answers
    the current state of the service: the same answer the proxy of the service
    itself gives, minus everything which is not the requested resource.

    Args:
        service (registry.models.service.Service): the registered service.
        element (registry.models.service.ServiceElement): a layer or feature type
            which belongs to the service.
        request (rest_framework.request.Request): the request of the client, to
            answer the urls of the document with.

    Returns:
        bytes: the capabilities document advertising only the given resource.

    Raises:
        CapabilitiesError: if the document can not be narrowed down.
    """
    try:
        document = service.get_capabilitites_for_request(request)
    except CapabilitiesError:
        raise
    except Exception:
        # the reason the mappers of the service failed is not part of the exception
        # report, which is answered to the client and may be read by anyone
        logger.exception(
            "The capabilities document of the service '%s' can not be generated.",
            service.pk,
        )
        raise CapabilitiesError(
            MALFORMED,
            "The capabilities document of the service can not be generated.",
            status=502,
        )
    return single_resource(document, service.service_type, element.identifier)


def element_capabilities_url(url_name, element_pk_kwarg, element_id,
                             request=None) -> str:
    """The address of the capabilities document which advertises only one resource.

    The url names the resource in its path and carries no query parameter: the
    endpoint reads the service of the resource out of the registry and answers
    the parameters of the capabilities request itself, so the url stays the same
    however a client uses it.

    Args:
        url_name (str): the name of the url of the endpoint, see MrMap/urls.py.
        element_pk_kwarg (str): the name of the path converter of the resource.
        element_id: the uuid of the layer or feature type.
        request: the request of the client, to answer an absolute url of. Without it,
            the path of the url is answered.

    Returns:
        str: the url of the capabilities document of the single resource.
    """
    return reverse(
        url_name,
        kwargs={element_pk_kwarg: element_id},
        request=request,
    )


def layer_capabilities_url(layer_id, request=None) -> str:
    """The url of the capabilities document which advertises only one WMS layer."""
    return element_capabilities_url(
        WMS_CAPABILITIES_URL, "layer_pk", layer_id, request=request
    )


def feature_type_capabilities_url(feature_type_id, request=None) -> str:
    """The url of the capabilities document which advertises only one WFS feature type."""
    return element_capabilities_url(
        WFS_CAPABILITIES_URL, "featuretype_pk", feature_type_id, request=request
    )
