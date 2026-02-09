from registry.enums.service import HttpMethodEnum, OGCOperationEnum
from registry.mappers.xml_mapper import XmlMapper
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


def operation_url_identifier(mapper: XmlMapper, instance: OperationUrl):
    xpath = f"./wms:Capability/wms:Request/wms:{OGCOperationEnum(instance.operation).label}/wms:DCPType/wms:HTTP/wms:{HttpMethodEnum(instance.method).label}"
    return xpath
