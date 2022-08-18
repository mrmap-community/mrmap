from eulxml.xmlmap.fields import _find_xml_node
from lxml import etree


def get_or_create_node(root_node, xpath, namespaces):

    branches = filter(None, xpath.split("/"))
    print(branches)
    # TODO: check if there are wildcards like "//" or "*"

    current_branch = ""
    current_node = root_node
    for branch in branches:
        current_branch += f"/{branch}"
        print(current_branch)
        match = _find_xml_node(xpath=current_branch,
                               node=current_node, context={"namespaces": namespaces})
        if len(match):
            current_node = etree.SubElement(
                current_node, branch, nsmap=namespaces)
