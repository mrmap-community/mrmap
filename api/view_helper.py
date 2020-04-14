"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 10.09.19

"""
from django.contrib.gis.geos import GEOSGeometry, Polygon
from django.db.models import Q

from MapSkinner.messages import PARAMETER_ERROR
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
    if pid is not None:
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
    if query is not None:
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
    if queryset is not None:
        queryset = queryset.order_by(
            order_by
        )
    return queryset


def filter_queryset_metadata_query(queryset, query):
    """ Filters a given REST framework queryset by a given query.

    Only keeps elements which title, abstract or keyword can be matched to the given query.

    Args:
        queryset: A queryset containing elements
        query: A text snippet which is used for a search
    Returns:
        queryset: The given queryset which only contains matching elements
    """
    if query is not None:
        # DRF automatically replaces '+' to ' ' whitespaces, so we work with this
        query_list = query.split(" ")
        q = Q()
        for query_elem in query_list:
            q &= Q(title__icontains=query_elem)\
                 | Q(abstract__icontains=query_elem)\
                 | Q(keywords__keyword__icontains=query_elem)

        queryset = queryset.filter(q).distinct()
    return queryset


def filter_queryset_metadata_inside_bbox(queryset, bbox: str, bbox_srs: str):
    """ Filters a given REST framework queryset by a given bbox.

    Filters for results, which are fully inside the bbox.

    Args:
        queryset: A queryset containing elements
        bbox: A bbox string (four coordinates)
        bbox_srs: Defines the reference system for the bbox
    Returns:
        queryset: The given queryset which only contains matching elements
    """
    if bbox is not None:
        try:
            srs = int(bbox_srs.split(":")[-1])
        except ValueError:
            # The srs is not valid
            raise Exception(PARAMETER_ERROR.format("bbox-srs"))

        if not isinstance(bbox, list):
            bbox = bbox.split(",")

        bbox = GEOSGeometry(Polygon.from_bbox(bbox), srid=srs)
        bbox.transform(DEFAULT_SRS)
        queryset = queryset.filter(
            bounding_geometry__contained=bbox
        )
    return queryset


def filter_queryset_metadata_intersects_bbox(queryset, bbox: str, bbox_srs: str):
    """ Filters a given REST framework queryset by a given bbox.

    Filters for results, which are partially inside the bbox.

    Args:
        queryset: A queryset containing elements
        bbox: A bbox string in EPSG:4326
        bbox_srs: Defines the reference system for the bbox
    Returns:
        queryset: The given queryset which only contains matching elements
    """
    if bbox is not None:
        try:
            srs = int(bbox_srs.split(":")[-1])
        except ValueError:
            # The srs is not valid
            raise Exception(PARAMETER_ERROR.format("bbox-srs"))

        if not isinstance(bbox, list):
            bbox = bbox.split(",")

        bbox = GEOSGeometry(Polygon.from_bbox(bbox), srid=srs)
        bbox.transform(DEFAULT_SRS)
        queryset = queryset.filter(
            bounding_geometry__bboverlaps=bbox
        )
    return queryset


def filter_queryset_metadata_service_type(queryset, type: str):
    """ Filters a given REST framework queryset by a given service type as string

    Args:
        queryset: A queryset containing elements
        type: A string of 'wms' or 'wfs'
    Returns:
        queryset: The given queryset which only contains matching elements
    """
    if type is not None:
        queryset = queryset.filter(
            service__servicetype__name=type
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
    if uuid is not None:
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
    if orgid is not None:
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
    if orgid is not None:
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
    if uuid is not None:
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
    if type is not None:
        queryset = queryset.filter(
            servicetype__name=type
        )
    return queryset