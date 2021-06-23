from django.forms import SelectMultiple
import json


class TreeSelectMultiple(SelectMultiple):
    template_name = "main/widgets/tree_select_multiple.html"

    def __init__(self, tree, *args, **kwargs):
        self.tree = tree
        choices = [(node.pk, node.pk) for node in tree]
        super().__init__(choices=choices, attrs={"hidden": True}, *args, **kwargs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name=name, value=value, attrs=attrs)

        data = []
        for node in self.tree:
            node_dict = {"id": str(node.pk),
                         "parent": str(node.parent_id) if node.parent_id else "#",
                         "text": node.metadata.title,}
            if value and node.pk in value:
                node_dict.update({"state": {"selected": True}})
            data.append(node_dict)
        json_data = json.dumps(data)

        context.update({"data": json_data.__str__()})
        return context
