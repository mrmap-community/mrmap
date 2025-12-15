from lxml import etree

def get_tag(element):
    """Returns the tag name without namespace."""
    if isinstance(element, etree._Element):
        return etree.QName(element).localname
    tag = element.tag
    if "}" in tag:
        tag = tag.split("}")[1]
    
    return tag
