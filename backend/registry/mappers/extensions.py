from collections import Counter

from mptt2.models import Node, Tree
from registry.exceptions.service import DuplicateLayerIdentifiers
from registry.models.service import Layer, OperationUrl


def split(context, value, token):
    values = []
    if isinstance(value, list):
        for v in value:
            values.extend(v.split(token))
    else:
        values = value.split(token)
    return values


def validate_unique_layer_identifiers(mapper):
    """Refuses a capabilities document which re-lists one layer name.

    A WMS may list the same ``<Name>`` under several parents (swisstopo
    BGDI, IGN geopf, geodienste.hamburg.de, #1200); ``registry.models.Layer``
    keeps one row per ``(service, identifier)``, so persisting such a
    document ended in a raw ``UniqueViolation`` deep inside the bulk insert
    and the whole registration failed with a constraint dump as the only
    user-facing message. #1200 decided these services stay refused - so this
    hook says so itself, naming the duplicated identifiers, before a single
    row is written.

    A layer without a ``<Name>`` is a legal grouping node; its NULL
    identifier never collides with another one and is not counted.
    """
    identifiers = Counter(
        inst.identifier
        for inst in mapper.read_all_from_cache().values()
        if isinstance(inst, Layer) and inst.identifier
    )
    duplicated = [name for name, count in identifiers.items() if count > 1]
    if duplicated:
        raise DuplicateLayerIdentifiers(duplicated)


def compute_layer_mptt(mapper):
    """
    Traversiert alle Layer-Instanzen aus dem Mapper-Cache und berechnet
    lft/rght/level Werte für MPTT2.
    """
    layers = [
        inst for inst in mapper.read_all_from_cache().values()
        if isinstance(inst, Node)
    ]  # flat list of all layers, ordered in the correct parsed direction.
    if not layers:
        return

    tree = Tree.objects.create()

    def assign_mptt(node, cursor=1, level=0):
        node.mptt_tree = tree
        node.mptt_depth = level
        node.mptt_lft = cursor
        cursor += 1  # wichtig: erst IN der Funktion erhöhen

        # Kinder ermitteln
        children = [layer for layer in layers if getattr(
            layer, "mptt_parent_id", None) == node.id]
        for child in children:
            cursor = assign_mptt(child, cursor, level + 1)

        node.mptt_rgt = cursor
        cursor += 1  # Abschluss des Knotens

        return cursor

    # Wurzelknoten finden
    root_node = next(layer for layer in layers if layer.mptt_parent is None)
    assign_mptt(root_node)


def clean_up_operation_urls(mapper):
    """
    throws away undefined operation urls.

    :param mapper: the mapper instance
    """

    def is_invalid_operation_url(inst):
        return (
            inst.method is None
            or not inst.url
            or not inst.operation
        )

    cache = mapper.read_all_from_cache()
    for key, inst in list(cache.items()):
        if inst is None or isinstance(inst, OperationUrl) and is_invalid_operation_url(inst):
            mapper.cache.delete(key)
