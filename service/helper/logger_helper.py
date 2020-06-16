"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 16.06.20

"""
from service.models import Metadata, ProxyLog
from service.tables import ProxyLogTable
from structure.models import MrMapUser


def prepare_proxy_log_filter(filter_params: dict, user: MrMapUser):
    """ Creates a ProxyLogTable object from filter parameters and a performing user

    Args:
        filter_params (dict): The parameter used for filtering
        user (dict): The parameter used for filtering
    Returns:
         proxy_log_table (ProxyLogTable)
    """
    user_groups = user.get_groups()
    group_metadatas = Metadata.objects.filter(created_by__in=user_groups)

    proxy_logs = ProxyLog.objects.filter(metadata__in=group_metadatas)
    proxy_log_table = ProxyLogTable(proxy_logs, user=user)
    proxy_log_table.filter_table(filter_params)

    return proxy_log_table
