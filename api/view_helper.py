"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 10.09.19

"""
from dateutil.parser import parse
from django.contrib.gis.geos import GEOSGeometry, Polygon
from django.db.models import Q

from MrMap.messages import PARAMETER_ERROR
from api.settings import API_QUERY_ON_TITLE, API_QUERY_ON_KEYWORDS, API_QUERY_ON_ABSTRACT
from service.models import Keyword
from service.settings import DEFAULT_SRS


def filter_queryset_service_pid(queryset, pid):
    """ Filters a given REST framework queryset by a given parent id.

    Only keeps elements which id matches the given parent id.

    Args:
        queryset: A queryset containing elements
        pid: An id which refers to a parent element
    Returns:
        queryset: The given queryset which only contains elements with a matching id
    """
    if pid is not None and len(pid) > 0:
        queryset = queryset.filter(
            parent_service__id=pid
        )
    return queryset


def filter_queryset_service_query(queryset, query):
    """ Filters a given REST framework queryset by a given query.

    Only keeps elements which title, abstract or keyword can be matched to the given query.

    Args:
        queryset: A queryset containing elements
        query: A text snippet which is used for a search
    Returns:
        queryset: The given queryset which only contains matching elements
    """
    if query is not None and len(query) > 0:
        # DRF automatically replaces '+' to ' ' whitespaces, so we work with this
        query_list = query.split(" ")
        q = Q()
        for query_elem in query_list:
            q &= Q(metadata__title__icontains=query_elem)\
                 | Q(metadata__abstract__icontains=query_elem)\
                 | Q(metadata__keywords__keyword__icontains=query_elem)

        queryset = queryset.filter(q).distinct()
    return queryset


def order_queryset(queryset, order_by):
    """ Orders a given REST framework queryset by a given order parameter.


    Args:
        queryset: A queryset containing elements
        order_by: A ordering identifier
    Returns:
        queryset: The given queryset which is ordered
    """
    if queryset is not None and len(order_by) > 0:
        queryset = queryset.order_by(
            order_by
        )
    return queryset


def create_keyword_query_filter(query):
    """ Creates a filter for the ORM

    Args:
        query: A text snippet which is used for a search
    Returns:
        filter (Q): A filter object
    """
    _filter = Q()
    if query is not None and len(query) > 0:
        _filter = Q(
            keyword__istartswith=query
        )
    return _filter


def create_category_query_filter(query):
    """ Creates a filter for the ORM

    Args:
        query: A text snippet which is used for a search
    Returns:
        filter (Q): A filter object
    """
    _filter = Q()
    if query is not None and len(query) > 0:
        _filter = Q(
            type__icontains=query
        ) | Q(
            title_locale_1__icontains=query
        ) | Q(
            title_locale_2__icontains=query
        ) | Q(
            title_EN__icontains=query
        )
    return _filter


def filter_queryset_metadata_query(queryset, query, q_test: bool = False):
    """ Filters a given REST framework queryset by a given query.

    Only keeps elements which title, abstract or keyword can be matched to the given query.

    Args:
        queryset: A queryset containing elements
        query: A text snippet which is used for a search
        q_test (bool): In case of tests, all query settings will be set to True
    Returns:
        queryset: The given queryset which only contains matching elements
    """
    if query is not None and len(query) > 0:
        if q_test:
            q_abstract = True
            q_keywords = True
            q_title = True
        else:
            q_abstract = API_QUERY_ON_ABSTRACT
            q_keywords = API_QUERY_ON_KEYWORDS
            q_title = API_QUERY_ON_TITLE

        # DRF automatically replaces '+' to ' ' whitespaces, so we work with this
        query_list = query.split(" ")
        q = Q()
        all_keywords = Keyword.objects.all()
        for query_elem in query_list:
            q_tmp = Q()
            if q_keywords:
                matching_keywords = all_keywords.filter(keyword__istartswith=query_elem)
                kws_exist = matching_keywords.exists()
                if kws_exist:
                    matching_keywords = matching_keywords.values_list("id")
                else:
                    matching_keywords = None
                q_tmp |= Q(keywords__id__in=matching_keywords)
            if q_title:
                q_tmp |= Q(title__icontains=query_elem)
            if q_abstract:
                q_tmp |= Q(abstract__icontains=query_elem)
            q &= q_tmp

        queryset = queryset.filter(q)
    return queryset


def filter_queryset_metadata_category(queryset, category, category_strict):
    """ Filters a given REST framework queryset by a given query.

    Only keeps elements which title, abstract or keyword can be matched to the given query.

    Args:
        queryset: A queryset containing elements
        category: A list of ids
        category_strict: Whether to evaluate multiple ids using AND or OR
    Returns:
        queryset: The given queryset which only contains matching elements
    """
    if category is not None and len(category) > 0:
        # DRF automatically replaces '+' to ' ' whitespaces, so we work with this
        category_list = category.split(" ")

        queryset = queryset.filter(
            categories__id__in=category_list
        ).distinct()
        if category_strict:
            for category in category_list:
                queryset = queryset.filter(categories__id=category)

    return queryset


def filter_queryset_metadata_dimension_time(queryset, time_min: str, time_max: str):
    """ Filters a given REST framework queryset by a time_min and time_max boundary.

    Only keeps the element which can be found in this temporal span.

    Args:
        queryset: A queryset containing elements
        time_min (str): The date in ISO format YYYY-mm-dd
        time_max (str): The date in ISO format YYYY-mm-dd
    Returns:
        queryset: The given queryset which only contains matching elements
    """
    if time_min is not None and len(time_min) > 0:
        time_min = parse(timestr=time_min)
        queryset = queryset.filter(
            dimensions__time_extent_min__gte=time_min
        )
    if time_max is not None and len(time_max) > 0:
        time_max = parse(timestr=time_max)
        queryset = queryset.filter(
            dimensions__time_extent_max__lte=time_max
        )

    return queryset


def filter_queryset_metadata_dimension_elevation(queryset, elev_min: str, elev_max: str, elevation_unit: str):
    """ Filters a given REST framework queryset by a time_min and time_max boundary.

    Only keeps the element which can be found in this temporal span.

    Args:
        queryset: A queryset containing elements
        elev_min (str): The date in ISO format YYYY-mm-dd
        elev_max (str): The date in ISO format YYYY-mm-dd
        elevation_unit (str): The elevation unit looking for
    Returns:
        queryset: The given queryset which only contains matching elements
    """
    if not elevation_unit:
        elevation_unit = ""
    if elev_min is not None and len(elev_min) > 0:
        queryset = queryset.filter(
            dimensions__units__icontains=elevation_unit,
            dimensions__elev_extent_min__lte=elev_min,
        )
    if elev_max is not None and len(elev_max) > 0:
        queryset = queryset.filter(
            dimensions__units__icontains=elevation_unit,
            dimensions__elev_extent_max__gte=elev_max,
        )

    return queryset


def filter_queryset_metadata_bbox(queryset, bbox: str, bbox_srs: str, bbox_strict: bool):
    """ Filters a given REST framework queryset by a given bbox.

    Args:
        queryset: A queryset containing elements
        bbox: A bbox string (four coordinates)
        bbox_srs: Defines the reference system for the bbox
        bbox_strict: Defines whether only results fully inside or intersected as well shall be returned
    Returns:
        queryset: The given queryset which only contains matching elements
    """
    if bbox is not None and len(bbox) > 0:
        try:
            srs = int(bbox_srs.split(":")[-1])
        except ValueError:
            # The srs is not valid
            raise Exception(PARAMETER_ERROR.format("bbox-srs"))

        if not isinstance(bbox, list):
            bbox = bbox.split(",")

        bbox = GEOSGeometry(Polygon.from_bbox(bbox), srid=srs)
        bbox.transform(DEFAULT_SRS)

        if bbox_strict:
            filter_identifier = "bounding_geometry__contained"
        else:
            filter_identifier = "bounding_geometry__bboverlaps"

        queryset = queryset.filter(
            **{filter_identifier: bbox}
        )
    return queryset


def filter_queryset_metadata_type(queryset, type: str):
    """ Filters a given REST framework queryset by a given service type as string

    Args:
        queryset: A queryset containing elements
        type: A string of 'wms' or 'wfs'
    Returns:
        queryset: The given queryset which only contains matching elements
    """
    filter_identifier = "service__service_type__name"
    single_types = [
        "dataset",
        "feature",
        "layer",
        "service"
    ]
    if type in single_types:
        filter_identifier = "metadata_type"
    if type is not None and len(type) > 0:
        queryset = queryset.filter(
            **{filter_identifier: type},
        )
    return queryset


def filter_queryset_metadata_uuid(queryset, uuid):
    """ Filters a given REST framework queryset by a given uuid.

    Only keeps the element which holds the uuid.

    Args:
        queryset: A queryset containing elements
        uuid: A uuid
    Returns:
        queryset: The given queryset which only contains matching elements
    """
    if uuid is not None and len(uuid) > 0:
        queryset = queryset.filter(
            uuid=uuid
        )
    return queryset


def filter_queryset_group_organization_id(queryset, orgid):
    """ Filters a given REST framework queryset by a given organization.

    Only keeps groups which are related to the organization.

    Args:
        queryset: A queryset containing elements
        orgid: An organization id
    Returns:
        queryset: The given queryset which only contains matching elements
    """
    if orgid is not None and len(orgid) > 0:
        queryset = queryset.filter(
            Q(organization=orgid)
        )
    return queryset


def filter_queryset_services_organization_id(queryset, orgid):
    """ Filters a given REST framework queryset by a given organization.

    Only keeps elements which are published by the organization that is referred using the id.

    Args:
        queryset: A queryset containing elements
        orgid: An organization id
    Returns:
        queryset: The given queryset which only contains matching elements
    """
    if orgid is not None and len(orgid) > 0:
        queryset = queryset.filter(
            Q(metadata__contact_id=orgid)
        )
    return queryset


def filter_queryset_services_uuid(queryset, uuid):
    """ Filters a given REST framework queryset by a uuid.

    Only keeps the element which has the given uuid.

    Args:
        queryset: A queryset containing an element
        uuid: A uuid
    Returns:
        queryset: The given queryset which only contains matching elements
    """
    if uuid is not None and len(uuid) > 0:
        queryset = queryset.filter(
            Q(uuid=uuid)
        )
    return queryset


def filter_queryset_real_organization(queryset, auto_generated: bool):
    """ Filters a given REST framework queryset for real (not auto generated) organizations.

    Only keeps organizations that are or not auto generated.

    Args:
        queryset: A queryset containing elements
        auto_generated (bool): Whether the real or auto generated organizations shall be returned
    Returns:
        queryset: The given queryset which only contains matching elements
    """
    if auto_generated is not None and isinstance(auto_generated, bool):
        queryset = queryset.filter(
            is_auto_generated=auto_generated
        )
    return queryset


def filter_queryset_service_type(queryset, type):
    """ Filters a given REST framework queryset by a given query.

    Only keeps elements which are of type 'type'.

    Args:
        queryset: A queryset containing elements
        type: A service type ('wms' or 'wfs')
    Returns:
        queryset: The given queryset which only contains matching elements
    """
    if type is not None and len(type) > 0:
        queryset = queryset.filter(
            service_type__name=type
        )
    return queryset