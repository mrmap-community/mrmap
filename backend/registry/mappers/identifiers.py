from registry.enums.service import HttpMethodEnum, OGCOperationEnum
from registry.models.service import Layer, OperationUrl


def layer_identifier(instance: Layer) -> str:
    """
    Recalculate the WMS Layer hierarchy using ONLY MPTT math.

    - No DB queries
    - No sibling iteration
    - No children access
    - Uses only mptt_parent, mptt_lft, mptt_rgt, mptt_depth
    - XPath indices are 0-based

    Returns:
    ./wms:Capability/wms:Layer[0]/wms:Layer[1]/wms:Layer[3]
    """

    # 1️⃣ Walk up the tree (self → root)
    chain: list[Layer] = []
    node = instance
    while node is not None:
        chain.append(node)
        node = node.mptt_parent

    chain.reverse()  # root → self

    xpath_parts = ["./wms:Capability"]

    # 2️⃣ Compute index at each level using ONLY mptt math
    for node in chain:
        xpath_parts.append(f"wms:Layer[{node.sibling_index + 1}]")

    xpath = "/".join(xpath_parts)
    return xpath


def operation_url_identifier(instance: OperationUrl):
    xpath = f"./wms:Capability/wms:Request/wms:{OGCOperationEnum(instance.operation).label}/wms:DCPType/wms:HTTP/wms:{HttpMethodEnum(instance.method).label}"
    return xpath
