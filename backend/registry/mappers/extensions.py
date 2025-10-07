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
    ]
    if not layers:
        return

    tree = Tree.objects.create()

    def assign_mptt(node, left=1, level=0):
        node.mptt_tree = tree
        node.mptt_depth = level
        node.mptt_lft = left
        right = left + 1

        # Kinder ermitteln
        children = [l for l in layers if getattr(
            l, "mptt_parent_id", None) == node.id]
        for child in children:
            right = assign_mptt(child, right, level + 1)

        node.mptt_rgt = right
        return right + 1

    # Wurzelknoten finden
    roots = [l for l in layers if l.mptt_parent is None]
    counter = 1
    for root in roots:
        counter = assign_mptt(root, counter, 0)
