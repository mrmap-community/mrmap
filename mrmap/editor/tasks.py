"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 29.07.20

"""
from celery import shared_task

from service.models import Metadata


@shared_task(name="async_process_securing_access")
def async_process_securing_access(md_id, use_proxy: bool, log_proxy: bool, restrict_access: bool):
    """ Performs processing of secured access form in an async call to celery

    Args:
        md_id (uuid): The metadata id
        use_proxy (bool): New proxy value
        log_proxy (bool): New proxy logging value
        restrict_access (bool): New restrict access value
    Returns:

    """
    metadata = Metadata.objects.select_related('service', 'featuretype').get(
        id=md_id
    )

    # Create list of main and sub metadatas for later use
    subelements = metadata.get_described_element().get_subelements().select_related('metadata') # could be list of layers or featuretypes

    if metadata.use_proxy_uri != use_proxy:
        metadata.set_proxy(use_proxy)

    if metadata.log_proxy_access != log_proxy:
        metadata.set_logging(log_proxy)

    if metadata.is_secured != restrict_access:
        metadata.set_secured(restrict_access)

    if restrict_access is False:
        metadata.allowed_operations.all().delete()
    # Clear cached documents
    ## There might be the case, that a user requests a subelements capability document just before the securing is finished
    ## In this case we would have a cached document with non-secured links and stuff - therefore we clear again in the end
    ## just to make sure!
    metadata.clear_cached_documents()

    for subelement in subelements:
        md = subelement.metadata
        if restrict_access is False:
            md.allowed_operations.all().delete()
        # Clear cached documents
        ## There might be the case, that a user requests a subelements capability document just before the securing is finished
        ## In this case we would have a cached document with non-secured links and stuff - therefore we clear again in the end
        ## just to make sure!
        md.clear_cached_documents()
