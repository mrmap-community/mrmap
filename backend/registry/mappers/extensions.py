from mptt2.models import Node, Tree


def split(context, value, token):
    values = []
    if isinstance(value, list):
        for v in value:
            values.extend(v.split(token))
    else:
        values = value.split(token)
    return values


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
