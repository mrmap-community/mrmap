"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 25.05.20

"""

from django.db.models import QuerySet, Q
from lxml.etree import Element, QName

from MrMap.settings import GENERIC_NAMESPACE_TEMPLATE
from service.helper import xml_helper

AND = " and "
OR = " or "
NEQ = " != "
EQ = " = "
LIKE = " like "
ILIKE = " ilike "

DJANGO_CONTAINS_TEMPLATE = "__{}contains"
DJANGO_STARTSWITH_TEMPLATE = "__{}startswith"
DJANGO_ENDSWITH_TEMPLATE = "__{}endswith"

FILTER_NOT_SUPPORTED_TEMPLATE = "{} is not supported for filtering. Choices are `{}`"
CONSTRAINT_LOCATOR = "constraint"

ATTRIBUTE_MAP = {
    "dc:title": "title",
    "dc:identifier": "identifier",
    "dc:subject": "keywords__keyword",
    "dc:abstract": "abstract",
    "dc:description": "abstract",
    "dc:date": "created",
    "dc:modified": "last_modified",
    "csw:AnyText": "keywords__keyword|title|abstract",
}


def filter_queryset(constraint: str, constraint_language: str, metadatas: QuerySet):
    """ Recursive filtering of queryset

    Args:
        constraint (str): The constraint string
        constraint_language (str): The language which defines the constraint syntax
        metadatas (QuerySet): The current queryset status
    Returns:
         metadatas (Queryset): The filtered queryset
    """
    # Make sure no ' or " can be found inside the constraint CQL!
    constraint = constraint.replace("'", "").replace('"', "")

    if AND in constraint:
        # Split each part of the AND relation and call the filter function again for each
        where_split = constraint.split(AND)
        filtered_qs = None
        for component in where_split:
            qs = filter_queryset(component, constraint_language, metadatas)
            if filtered_qs is None:
                filtered_qs = qs
            # Using .intersection() we only get the query elements which can be found in both querysets (which is AND)
            filtered_qs = filtered_qs.intersection(qs)
        metadatas = filtered_qs
    elif OR in constraint:
        # recursion!
        where_split = constraint.split(OR)
        filtered_qs = None
        for component in where_split:
            qs = filter_queryset(component, constraint_language, metadatas)
            if filtered_qs is None:
                filtered_qs = qs
            # Using .union() we merge the resulting query elements into one queryset (which is OR)
            filtered_qs = filtered_qs.union(qs)
        metadatas = filtered_qs
    else:
        # No further recursion needed, filter directly
        metadatas = filter_col(constraint, metadatas)
        return metadatas
    return metadatas


def filter_col(where: str, metadatas: QuerySet):
    """ Filter by column name

    Mocked columns will be mapped on the real nested accessor

    Args:
        where (str): The WHERE sql style string
        metadatas (QuerySet): The metadata queryset
    Returns:
        metadatas (QuerySet): The filtered queryset
    """
    exclude = {}
    filter = {}

    if NEQ in where:
        where_list = where.split(NEQ)
        key = where_list[0].strip()
        val = where_list[-1].strip()

        # Resolve mocked column name in key to real nested attribute, if the col is mocked
        attribute_key = ATTRIBUTE_MAP.get(key, None)
        if attribute_key is None:
            raise ValueError(FILTER_NOT_SUPPORTED_TEMPLATE.format(key, ", ".join(ATTRIBUTE_MAP.keys())), CONSTRAINT_LOCATOR)
        exclude = {identifier: val for identifier in attribute_key.split("|")}

    elif EQ in where:
        where_list = where.split(EQ)
        key = where_list[0].strip()
        val = where_list[-1].strip()

        # Resolve mocked column name in key to real nested attribute, if the col is mocked
        attribute_key = ATTRIBUTE_MAP.get(key, None)
        if attribute_key is None:
            raise ValueError(FILTER_NOT_SUPPORTED_TEMPLATE.format(key, ", ".join(ATTRIBUTE_MAP.keys())), CONSTRAINT_LOCATOR)
        filter = {identifier: val for identifier in attribute_key.split("|")}

    elif LIKE in where:
        where_list = where.split(LIKE)
        key = where_list[0].strip()
        val = where_list[-1].strip()

        # For LIKE we must resolve the correct django filter suffix (__contains, __startswith, __endswith)
        filter_suffix = resolve_filter_suffix(False, val)

        # Get rid of the '%' since we do not need it in django style filtering
        val = val.replace("%", "")

        # Resolve mocked column name in key to real nested attribute, if the col is mocked
        attribute_key = ATTRIBUTE_MAP.get(key, None)
        if attribute_key is None:
            raise ValueError(FILTER_NOT_SUPPORTED_TEMPLATE.format(key, ", ".join(ATTRIBUTE_MAP.keys())), FILTER_NOT_SUPPORTED_TEMPLATE)
        filter = {identifier + filter_suffix: val for identifier in attribute_key.split("|")}

    elif ILIKE in where:
        where_list = where.split(ILIKE)
        key = where_list[0].strip()
        val = where_list[-1].strip()

        # For ILIKE we must resolve the correct django filter suffix (__icontains, __istartswith, __iendswith)
        filter_suffix = resolve_filter_suffix(True, val)

        # Get rid of the '%' since we do not need it in django style filtering
        val = val.replace("%", "")

        # Resolve mocked column name in key to real nested attribute, if the col is mocked
        attribute_key = ATTRIBUTE_MAP.get(key, None)
        if attribute_key is None:
            raise ValueError(FILTER_NOT_SUPPORTED_TEMPLATE.format(key, ", ".join(ATTRIBUTE_MAP.keys())), CONSTRAINT_LOCATOR)
        filter = {identifier + filter_suffix: val for identifier in attribute_key.split("|")}

    # Restructure filter using Q() for case of '|' separated real columns.
    # For other cases this won't hurt anyone.
    q_filter = Q()
    for item in filter:
        q_filter |= Q(**{item: filter[item]})

    metadatas = metadatas.filter(
        q_filter
    ).exclude(
        **exclude
    )
    return metadatas


def resolve_filter_suffix(is_insensitive: bool, val: str):
    """ Resolves django filter suffix from SQL '%' position in val.

    '%test'     -> endswith test
    'test%'     -> startswith test
    '%test%'     -> contains test

    Args:
        is_insensitive (bool): Whether insensitivity is used or not
        val (str): The lookup string containing "%"
    Returns:
         filter_suffix (str): The django style filter suffix
    """
    filter_suffix = None
    sensitive = "i" if is_insensitive else ""
    if val.startswith("%") and val.endswith("%"):
        filter_suffix = DJANGO_CONTAINS_TEMPLATE.format(sensitive)
    elif val.startswith("%"):
        filter_suffix = DJANGO_ENDSWITH_TEMPLATE.format(sensitive)
    elif val.endswith("%"):
        filter_suffix = DJANGO_STARTSWITH_TEMPLATE.format(sensitive)
    return filter_suffix


def transform_constraint_to_cql(constraint: str, constraint_language: str):
    """ Transforms a xml filter style constraint into CQL style

    Args:
        constraint (str): The constraint parameter
        constraint_language (str): The constraintlanguage parameter
    Returns:
         constraint (str): The transfored constrained
    """
    if constraint_language.upper() != "FILTER":
        raise ValueError("{} is no valid CSW conform value. Choices are `CQL_TEXT, FILTER`".format(constraint_language), "constraintlanguage")

    constraint_xml = xml_helper.parse_xml(constraint)
    if constraint_xml is None:
        raise ValueError("Constraint value is no valid xml! Did you set the correct value for 'constraintlanguage'?", CONSTRAINT_LOCATOR)
    filter_elem = xml_helper.try_get_single_element_from_xml("//" + GENERIC_NAMESPACE_TEMPLATE.format("Filter"), constraint_xml.getroot())
    new_constraint = _transform_constraint_to_cql_recursive(filter_elem)

    return new_constraint


def _transform_constraint_to_cql_recursive(upper_elem: Element):
    constraints = []

    connector_tags = [
        "and",
        "or",
        "not"
    ]
    # Prevent <ogc:Filter> from being used as upper_tag joiner in the end
    upper_tag = QName(upper_elem).localname.lower()
    upper_tag = upper_tag if upper_tag in connector_tags else ""
    elements = upper_elem.getchildren()

    for child in elements:
        child_tag = QName(child).localname
        if child_tag.lower() in connector_tags:
            constraints.append(_transform_constraint_to_cql_recursive(child))
        else:
            property_name = xml_helper.try_get_text_from_xml_element(elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("PropertyName"), xml_elem=child)
            literal = xml_helper.try_get_text_from_xml_element(elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("Literal"), xml_elem=child)
            expr = ""
            if child_tag == "PropertyIsLike":
                expr = "like"
                wild_card = xml_helper.try_get_attribute_from_xml_element(child, "wildCard")
                literal = literal.replace(wild_card, "%")
            elif child_tag == "PropertyIsEqualTo":
                expr = "="
            elif child_tag == "PropertyIsNotEqualTo":
                expr = "!="
            elif child_tag == "PropertyIsGreaterThanOrEqualTo":
                expr = ">="
            elif child_tag == "PropertyIsGreaterThan":
                expr = ">"
            elif child_tag == "PropertyIsLessThanOrEqualTo":
                expr = "<="
            elif child_tag == "PropertyIsLessThan":
                expr = "<"
            else:
                raise ValueError("Unsupported {} found!".format(child_tag), "Filter")
            constraints.append("{} {} {}".format(property_name, expr, literal))
    constraint = " {} ".format(upper_tag).join(constraints)
    return constraint