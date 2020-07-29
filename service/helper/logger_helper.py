"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 16.06.20

"""
from django.http import HttpRequest

from service.filters import ProxyLogTableFilter
from service.models import Metadata, ProxyLog
from service.tables import ProxyLogTable
from structure.models import MrMapUser


def prepare_proxy_log_filter(request: HttpRequest, user: MrMapUser, current_view: str):
    """ Creates a ProxyLogTable object from filter parameters and a performing user

    Args:
        request (HttpRequest): The parameter used for filtering
        user (dict): The parameter used for filtering
    Returns:
         proxy_log_table (ProxyLogTable)
    """
    user_groups = user.get_groups()
    group_metadatas = Metadata.objects.filter(created_by__in=user_groups)

    queryset = ProxyLog.objects.filter(
        metadata__in=group_metadatas
    ).prefetch_related(
        "metadata"
    )

    return ProxyLogTable(request=request,
                         queryset=queryset,
                         filter_set_class=ProxyLogTableFilter,
                         current_view=current_view,
                         param_lead='logs-t',)
