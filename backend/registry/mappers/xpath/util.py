#   Copyright 2025 Center for Digital Humanities, Princeton University
#   Copyright 2010,2011 Emory University Libraries (eulxml)
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

from lxml import etree
from lxml.builder import ElementMaker

from . import ast
from .core import serialize


def _find_terminal_step(xast: ast.AST) -> ast.Step:
    if isinstance(xast, ast.Step):
        return xast
    elif isinstance(xast, ast.BinaryExpression):
        if xast.op in ("/", "//"):
            return _find_terminal_step(xast.right)
    raise Exception("Cannot find terminal step for xpath: %s" % serialize(xast))

def find_xml_node(xpath: str, node: etree.Element, context: dict) -> etree.Element | None:
    # In some cases the this will return a value not a node
    matches = node.xpath(xpath, **context)
    if matches and isinstance(matches, list):
        return matches[0]
    elif matches:
        return matches

def create_xml_node(xast: ast.AST, node: etree.Element, context: dict, insert_index=None) -> etree.Element:
    if isinstance(xast, ast.Step):
        if isinstance(xast.node_test, ast.NameTest):
            # check the predicates (if any) to verify they're constructable
            for pred in xast.predicates:
                if not _predicate_is_constructible(pred):
                    msg = (
                        "Missing element for '%s', and node creation is "
                        + "supported only for simple child and attribute "
                        + "nodes with simple predicates."
                    ) % (serialize(xast),)
                    raise Exception(msg)

            # create the node itself
            if xast.axis in (None, "child"):
                new_node = _create_child_node(node, context, xast, insert_index)
            elif xast.axis in ("@", "attribute"):
                new_node = _create_attribute_node(node, context, xast)
            else:
                msg = (
                    "Missing element for '%s', and node creation is "
                    + "supported only for child and attribute nodes."
                ) % (serialize(xast),)
                raise Exception(msg)

            # and create any nodes necessary for the predicates
            for pred in xast.predicates:
                _construct_predicate(pred, new_node, context)

            return new_node

        # if this is a text() node, we don't need to create anything further
        # return the node that will be parent to text()
        elif _is_text_nodetest(xast):
            return node

    elif isinstance(xast, ast.BinaryExpression):
        if xast.op == "/":
            left_xpath = serialize(xast.left)
            left_node = find_xml_node(left_xpath, node, context)
            if left_node is None:
                left_node = create_xml_node(xast.left, node, context)
            return create_xml_node(xast.right, left_node, context)

    # anything else, throw an exception:
    msg = (
        "Missing element for '%s', and node creation is supported "
        + "only for simple child and attribute nodes."
    ) % (serialize(xast),)
    raise Exception(msg)

def _create_child_node(node: etree.Element, context: dict, step: ast.Step, insert_index=None) -> etree.Element:
    opts = {}
    ns_uri = None
    if "namespaces" in context:
        opts["nsmap"] = context["namespaces"]
        if step.node_test.prefix:
            ns_uri = context["namespaces"][step.node_test.prefix]
    E = ElementMaker(namespace=ns_uri, **opts)
    new_node = E(step.node_test.name)
    if insert_index is not None:
        node.insert(insert_index, new_node)
    else:
        node.append(new_node)
    return new_node

def _create_attribute_node(node: etree.Element, context: dict, step: ast.Step) -> etree.Element:
    node_name, node_xpath, nsmap = _get_attribute_name(step, context)
    # create an empty attribute node
    node.set(node_name, "")
    # find via xpath so a 'smart' string can be returned and set normally
    result = node.xpath(node_xpath, namespaces=nsmap)
    return result[0]

def _predicate_is_constructible(pred: ast.AST) -> bool:
    if isinstance(pred, ast.Step):
        # only child and attribute for now
        if pred.axis not in (None, "child", "@", "attribute"):
            return False
        # no node tests for now: only name tests
        if not isinstance(pred.node_test, ast.NameTest):
            return False
        # only constructible if its own predicates are
        return all(_predicate_is_constructible(sub_pred) for sub_pred in pred.predicates)
    elif isinstance(pred, ast.BinaryExpression):
        if pred.op == "/":
            # path expressions are constructible if each side is
            return _predicate_is_constructible(pred.left) and _predicate_is_constructible(pred.right)
        elif pred.op == "=":
            # = expressions are constructible for now only if the left side
            # is constructible and the right side is a literal or variable
            return _predicate_is_constructible(pred.left) and isinstance(pred.right, (int, str, ast.VariableReference))

    # otherwise, i guess we're ok
    return True

def _construct_predicate(xast: ast.AST, node: etree.Element, context: dict) -> etree.Element:
    if isinstance(xast, ast.Step):
        return create_xml_node(xast, node, context)
    elif isinstance(xast, ast.BinaryExpression):
        if xast.op == "/":
            left_leaf = _construct_predicate(xast.left, node, context)
            right_node = _construct_predicate(xast.right, left_leaf, context)
            return right_node
        elif xast.op == "=":
            left_leaf = _construct_predicate(xast.left, node, context)
            step = _find_terminal_step(xast.left)
            if isinstance(xast.right, ast.VariableReference):
                name = xast.right.name
                ctxval = context.get(name, None)
                if ctxval is None:
                    ctxval = context[name[1]]
                xvalue = str(ctxval)
            else:
                xvalue = str(xast.right)
            _set_in_xml(left_leaf, xvalue, context, step)
            return left_leaf
    raise Exception("Cannot construct predicate for xpath: %s" % serialize(xast))

def _set_in_xml(node: etree.Element, val, context: dict, step: ast.Step):
    # node could be either an element or an attribute
    if isinstance(node, etree._Element):  # if it's an element
        if isinstance(val, etree._Element):
            # remove node children and graft val children in.
            node.clear()
            node.text = val.text
            for child in val:
                node.append(child)
            for name, val in val.attrib.iteritems():
                node.set(name, val)
        else:  # set node contents to string val
            if not list(node):  # no child elements
                node.text = val
            else:
                raise Exception("Cannot set string value - not a text node!")

    # by default, etree returns a "smart" string for attributes and text.
    # if it's not an element (above) then it is either a text node
    # or an attribute
    elif hasattr(node, "getparent"):
        # if node test is text(), set the text of the parent node
        if _is_text_nodetest(step):
            node.getparent().text = val

        # otherwise, treat it as an attribute
        else:
            attribute, node_xpath, nsmap = _get_attribute_name(step, context)
            node.getparent().set(attribute, val)

def _get_attribute_name(step: ast.Step, context: dict) -> tuple[str, str, dict]:
    # calculate attribute name, xpath, and nsmap based on node info and context namespaces
    if not step.node_test.prefix:
        nsmap = {}
        ns_uri = None
        node_name = step.node_test.name
        node_xpath = "@%s" % node_name
    else:
        # if node has a prefix, the namespace *should* be defined in context
        if "namespaces" in context and step.node_test.prefix in context["namespaces"]:
            ns_uri = context["namespaces"][step.node_test.prefix]
        else:
            ns_uri = None
            # we could throw an exception here if ns_uri wasn't found, but
            # for now assume the user knows what he's doing...

        node_xpath = "@%s:%s" % (step.node_test.prefix, step.node_test.name)
        node_name = "{%s}%s" % (ns_uri, step.node_test.name)
        nsmap = {step.node_test.prefix: ns_uri}

    return node_name, node_xpath, nsmap

def _is_text_nodetest(step: ast.Step) -> bool:
    """Fields selected with an xpath of text() need special handling; Check if
    a xpath step is a text() node test."""
    try:
        return step.node_test.name == "text"
    except Exception:
        pass
    return False