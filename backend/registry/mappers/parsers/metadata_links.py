""" Serialize the metadata references a service element publishes.

    A service element publishes the metadata references it knows: the links which were
    imported from the capabilities document (`remote_metadata`) and the curated links a
    curator added in MrMap (see
    :attr:`registry.models.metadata.MetadataRelation.is_publishable`).

    Both kinds are rendered by the reverse mapping of the ``remote_metadata`` field of a
    layer / feature type, which gets its instances from
    :meth:`registry.models.service.ServiceElement.published_metadata_links`.

    The required information of a metadata reference differs between the protocols:

    * WMS 1.1.1 / 1.3.0: ``<!ELEMENT MetadataURL (Format, OnlineResource)>`` with a
      required ``type`` attribute (NMTOKEN). See
      https://schemas.opengis.net/wms/1.3.0/capabilities_1_3_0.xsd and
      https://schemas.opengis.net/wms/1.1.1/capabilities_1_1_1.dtd
    * WFS 2.0.0: ``MetadataURLType`` is an empty element with the xlink attributes only.
      See ``registry/ows_lib/xml/schemas/wfsCapabilitites200.xsd``.

    A reference which MrMap creates on its own always provides the required information.
    A reference which was imported keeps the type and format information of the source
    document as long as it is complete.
"""

from dataclasses import dataclass

from lxml import etree

# The metadata references MrMap publishes point to an iso 19115 metadata document.
METADATA_URL_TYPE = "TC211"
METADATA_URL_FORMAT = "application/xml"

XLINK_HREF = "{http://www.w3.org/1999/xlink}href"

# Elements which the schema defines after the MetadataURL element of a WMS layer. The
# wms 1.1.1 DTD additionally defines ScaleHint between Style and MinScaleDenominator.
WMS_METADATA_URL_FOLLOWERS = (
    "DataURL",
    "FeatureListURL",
    "Style",
    "ScaleHint",
    "MinScaleDenominator",
    "MaxScaleDenominator",
    "Layer",
)

# Elements which the schema defines after the MetadataURL element of a WFS feature type.
WFS_METADATA_URL_FOLLOWERS = ("ExtendedDescription",)


@dataclass(frozen=True)
class PublishedMetadataLink:
    """ A single metadata reference which is published for a service element.

        The reverse mapping only needs the attributes of this dataclass, it does not
        persist anything.
    """
    link: str
    metadata_type: str = METADATA_URL_TYPE
    metadata_format: str = METADATA_URL_FORMAT


def _localname(element) -> str:
    """ Return the local name of the tag of the given element. """
    return etree.QName(element).localname


def _children(element) -> list:
    """ Return all direct children of the given element as list. """
    return list(element.iterchildren())


def _position_element_before(element, follower_localnames: tuple):
    """ Move the given element to the position the schema defines for it.

        New elements are added at the end of their parent by the generic element
        creation, which is mostly not the position the schema requires. The element is
        only moved if it currently sits *after* an element which must follow it, so any
        already correct document is left untouched and repeated rendering is stable.
    """
    parent = element.getparent()
    if parent is None:
        return

    children = _children(parent)
    index = children.index(element)
    for position, child in enumerate(children):
        if _localname(child) in follower_localnames:
            if position < index:
                child.addprevious(element)
            return


def _ensure_child(parent, localname: str, text: str, insert_before) -> None:
    """ Ensure that a child element with the given local name exists in parent. """
    for child in parent.iterchildren():
        if _localname(child) == localname:
            return
    namespace = etree.QName(parent).namespace
    tag = f"{{{namespace}}}{localname}" if namespace else localname
    new_element = etree.Element(tag)
    new_element.text = text
    insert_before.addprevious(new_element)


def serialize_wms_metadata_url(mapper, element, instance: PublishedMetadataLink):
    """ Reverse parser of the ``remote_metadata`` field of a WMS layer.

        The mapper matched or created the ``wms:OnlineResource`` of the metadata
        reference, this parser ensures that the ``MetadataURL`` element which holds it
        is a complete and correctly positioned reference.

        :param mapper: the xml mapper which renders the document
        :param element: the wms:OnlineResource element of this reference
        :param instance: the published link which is rendered
    """
    carrier = element.getparent()
    if carrier is None or _localname(carrier) != "MetadataURL":
        # should not happen, the base xpath of the field always selects the
        # OnlineResource inside a MetadataURL element.
        element.set(XLINK_HREF, instance.link)
        return

    online_resources = [
        child for child in _children(carrier) if _localname(child) == "OnlineResource"]
    if len(online_resources) > 1:
        # The generic element creation reuses the first MetadataURL element it finds.
        # Each metadata reference is a MetadataURL element of its own.
        new_carrier = etree.Element(carrier.tag)
        carrier.addnext(new_carrier)
        new_carrier.append(element)
        carrier = new_carrier

    element.set(XLINK_HREF, instance.link)
    if "type" not in carrier.attrib:
        carrier.set("type", instance.metadata_type)
    _ensure_child(carrier, "Format", instance.metadata_format, element)
    _position_element_before(carrier, WMS_METADATA_URL_FOLLOWERS)


def serialize_wfs_metadata_url(mapper, element, instance: PublishedMetadataLink):
    """ Reverse parser of the ``remote_metadata`` field of a WFS feature type.

        :param mapper: the xml mapper which renders the document
        :param element: the wfs:MetadataURL element of this reference
        :param instance: the published link which is rendered
    """
    element.set(XLINK_HREF, instance.link)
    _position_element_before(element, WFS_METADATA_URL_FOLLOWERS)
