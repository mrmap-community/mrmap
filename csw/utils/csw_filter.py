"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 25.05.20

"""
from django.db.models import QuerySet, Q

AND = " and "
OR = " or "
NEQ = " != "
EQ = " = "
LIKE = " like "
ILIKE = " ilike "

DJANGO_CONTAINS_TEMPLATE = "__{}contains"
DJANGO_STARTSWITH_TEMPLATE = "__{}startswith"
DJANGO_ENDSWITH_TEMPLATE = "__{}endswith"

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


def prefilter_queryset(where: str, metadatas: QuerySet):
    """ Recursive filtering of queryset

    Args:
        where (str): The WHERE in sql style string
        metadatas (QuerySet): The current queryset status
    Returns:
         metadatas (Queryset): The filtered queryset
    """
    if AND in where:
        # Split each part of the AND relation and call the filter function again for each
        where_split = where.split(AND)
        filtered_qs = None
        for component in where_split:
            qs = prefilter_queryset(component, metadatas)
            if filtered_qs is None:
                filtered_qs = qs
            # Using .intersection() we only get the query elements which can be found in both querysets (which is AND)
            filtered_qs = filtered_qs.intersection(qs)
        metadatas = filtered_qs
    elif OR in where:
        # recursion!
        where_split = where.split(OR)
        filtered_qs = None
        for component in where_split:
            qs = prefilter_queryset(component, metadatas)
            if filtered_qs is None:
                filtered_qs = qs
            # Using .union() we merge the resulting query elements into one queryset (which is OR)
            filtered_qs = filtered_qs.union(qs)
        metadatas = filtered_qs
    else:
        # No further recursion needed, filter directly
        metadatas = filter_col(where, metadatas)
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
            raise ValueError("{} is not supported for filtering. Choices are `{}`".format(key, ", ".join(ATTRIBUTE_MAP.keys())), "constraint")
        exclude = {identifier: val for identifier in attribute_key.split("|")}

    elif EQ in where:
        where_list = where.split(EQ)
        key = where_list[0].strip()
        val = where_list[-1].strip()

        # Resolve mocked column name in key to real nested attribute, if the col is mocked
        attribute_key = ATTRIBUTE_MAP.get(key, None)
        if attribute_key is None:
            raise ValueError("{} is not supported for filtering. Choices are `{}`".format(key, ", ".join(ATTRIBUTE_MAP.keys())), "constraint")
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
            raise ValueError("{} is not supported for filtering. Choices are `{}`".format(key, ", ".join(ATTRIBUTE_MAP.keys())), "constraint")
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
            raise ValueError("{} is not supported for filtering. Choices are `{}`".format(key, ", ".join(ATTRIBUTE_MAP.keys())), "constraint")
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
