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


def prepare_proxy_log_filter(request: HttpRequest, user: MrMapUser):
    """ Creates a ProxyLogTable object from filter parameters and a performing user

    Args:
        request (HttpRequest): The parameter used for filtering
        user (dict): The parameter used for filtering
    Returns:
         proxy_log_table (ProxyLogTable)
    """
    user_groups = user.get_groups()
    group_metadatas = Metadata.objects.filter(created_by__in=user_groups)

    proxy_logs = ProxyLog.objects.filter(metadata__in=group_metadatas)

    proxy_logs_filtered = ProxyLogTableFilter(request.GET, queryset=proxy_logs)
    proxy_log_table = ProxyLogTable(proxy_logs_filtered.qs,
                                    user=user)
    proxy_log_table.filter = proxy_logs_filtered
    # TODO: # since parameters could be changed directly in the uri, we need to make sure to avoid problems
    proxy_log_table.configure_pagination(request, 'logs-t')

    return proxy_log_table
