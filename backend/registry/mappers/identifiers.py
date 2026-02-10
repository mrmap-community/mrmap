from registry.enums.iso import CategoryChoices, LanguageChoices
from registry.enums.service import HttpMethodEnum, OGCOperationEnum
from registry.mappers.xml_mapper import XmlMapper
from registry.models.metadata import (IsoCategory, Language, ReferenceSystem,
                                      TimeExtent)
from registry.models.service import Layer, OperationUrl, WebMapService


def layer_identifier(mapper: XmlMapper, instance: Layer) -> str:
    """
    Recalculate the WMS Layer hierarchy using precalculated sibling_index by Window annotation

    - No DB queries
    - No sibling iteration
    - No children access
    - Uses only mptt_parent, sibling_index (Windows annotation)
    - XPath indices are 0-based

    Returns:
    ./wms:Capability/wms:Layer[0]/wms:Layer[1]/wms:Layer[3]
    """
    if isinstance(mapper.db_instance, WebMapService):
        # we assume that db_instance was fetched by WebMapService.objects.prefetch_whole_service()
        # In that case any layer has sibling_index annotation
        # And any layer has a prefetch parent with sibling_index annotation too
        layers_map = {
            layer.id: layer for layer in mapper.db_instance.layers.all()}

        # 1️⃣ Walk up the tree (self → root)
        chain: list[Layer] = []
        node = layers_map.get(instance.pk)
        while node is not None:
            chain.append(node)
            node = layers_map.get(
                node.mptt_parent.pk) if node.mptt_parent else None

        chain.reverse()  # root → self

        xpath_parts = ["./wms:Capability"]

        # 2️⃣ Compute index at each level using ONLY mptt math
        for node in chain:
            xpath_parts.append(f"wms:Layer[{node.sibling_index + 1}]")

        xpath = "/".join(xpath_parts)
        return xpath


def wms_operation_url_identifier(mapper: XmlMapper, instance: OperationUrl):
    if mapper.mapping.get("_namespaces", {}).get("wms", None):
        xpath = f"./wms:Capability/wms:Request/wms:{OGCOperationEnum(instance.operation).label}/wms:DCPType/wms:HTTP/wms:{HttpMethodEnum(instance.method).label}"
    else:
        xpath = f"./Capability/Request/{OGCOperationEnum(instance.operation).label}/DCPType/HTTP/{HttpMethodEnum(instance.method).label}"
    return xpath


def wfs_operation_url_identifier(mapper: XmlMapper, instance: OperationUrl):
    xpath = f"./ows:OperationsMetadata/ows:Operation[@name='{OGCOperationEnum(instance.operation).label}']/ows:DCP/ows:HTTP/ows:{HttpMethodEnum(instance.method).label}"
    return xpath


def wfs_default_reference_system_identifier(mapper: XmlMapper, instance: ReferenceSystem):
    xpath = f"./wfs:DefaultCRS[text()='urn:ogc:def:crs:{instance.prefix.upper()}::{instance.code}']"
    return xpath


def wfs_other_reference_system_identifier(mapper: XmlMapper, instance: ReferenceSystem):
    xpath = f"./wfs:OtherCRS[text()='urn:ogc:def:crs:{instance.prefix.upper()}::{instance.code}']"
    return xpath


def language_identifier(mapper: XmlMapper, instance: Language):
    xpath = f"./gmd:language/gmd:LanguageCode[@codeList='http://www.loc.gov/standards/iso639-2/'][@codeListValue='{LanguageChoices(instance.value).label}']"
    return xpath


def refence_system_identifier(mapper: XmlMapper, instance: ReferenceSystem):
    xpath = f"./gmd:referenceSystemInfo/gmd:MD_ReferenceSystem/gmd:referenceSystemIdentifier/gmd:RS_Identifier/gmd:code/gco:CharacterString/text()='http://www.opengis.net/def/crs/{instance.prefix.upper()}/0/{instance.code}'"
    return xpath


def category_identifier(mapper: XmlMapper, instance: IsoCategory):
    xpath = f"./gmd:identificationInfo/gmd:MD_DataIdentification/gmd:topicCategory/gmd:MD_TopicCategoryCode/text()='{CategoryChoices(instance.value).label}'"
    return xpath


def timeextent_identifier(mapper: XmlMapper, instance: TimeExtent):
    # ./gmd:identificationInfo/srv:SV_ServiceIdentification/srv:extent/gmd:EX_Extent/gmd:temporalElement/gmd:EX_TemporalExtent/gmd:extent
    # ./gmd:identificationInfo/gmd:MD_DataIdentification/gmd:extent/gmd:EX_Extent/gmd:temporalElement/gmd:EX_TemporalExtent/gmd:extent
    xpath = f""
    return xpath
