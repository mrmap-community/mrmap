"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 10.09.19

"""
from django.db.models import Q


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
        queryset = queryset.filter(
            Q(metadata__title__icontains=query) |
            Q(metadata__abstract__icontains=query) |
            Q(metadata__keywords__keyword=query)
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


def filter_queryset_real_organization(queryset, auto_generated):
    """ Filters a given REST framework queryset for real (not auto generated) organizations.

    Only keeps organizations that are or not auto generated.

    Args:
        queryset: A queryset containing elements
        auto_generated: Whether the real or auto generated organizations shall be returned
    Returns:
        queryset: The given queryset which only contains matching elements
    """
    if auto_generated is not None:
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