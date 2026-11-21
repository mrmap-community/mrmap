from lxml import etree
from registry.helper.xml import parse_untrusted
from pygeofilter import ast
from pygeofilter.parsers.fes.util import Element, ElementTree
from pygeofilter.parsers.fes.v20 import FES20Parser

from .v11.parser import FES11Parser


def parse(xml: str | Element | ElementTree) -> ast.Node:
    """Workaround for missing PropertyName handling in fes 11 parser"""

    if isinstance(xml, str):
        root = parse_untrusted(xml)
    else:
        root = xml

    # decide upon namespace which parser to use
    namespace = etree.QName(root).namespace
    if namespace == FES11Parser.namespace:
        return FES11Parser().parse(root)
    elif namespace == FES20Parser.namespace:
        return FES20Parser().parse(root)

    raise ValueError(f"Unsupported namespace {namespace}")
