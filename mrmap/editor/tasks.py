"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 29.07.20

"""
from celery import shared_task, current_task, states
from celery.result import AsyncResult
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
    metadata = Metadata.objects\
        .select_related('service',
                        'featuretype',
                        'service__parent_service',
                        'service__parent_service__metadata')\
        .prefetch_related('documents')\
        .get(id=md_id)
    if current_task:
        current_task.update_state(
            state=states.STARTED,
            meta={
                "current": 0,
                "service": metadata.__str__(),
                "phase": "collecting sub elements of the service",
            }
        )

    # Create list of main and sub metadatas for later use
    subelements = metadata.get_described_element()\
                          .get_subelements()\
                          .select_related('metadata')\
                          .prefetch_related('metadata__documents')  # could be list of layers or featuretypes
    all_elements_count = len(subelements) + 1
    if current_task:
        current_task.update_state(
            state=states.STARTED,
            meta={
                "current": 0,
                "phase": "update use proxy setting of service elements",
            }
        )

    if metadata.use_proxy_uri != use_proxy:
        metadata.set_proxy(use_proxy)
    if current_task:
        current_task.update_state(
            state=states.STARTED,
            meta={
                "current": 0,
                "phase": "update log proxy access setting of service elements",
            }
        )

    if metadata.log_proxy_access != log_proxy:
        metadata.set_logging(log_proxy)
    if current_task:
        current_task.update_state(
            state=states.STARTED,
            meta={
                "phase": "update secure flag of service elements",
            }
        )

    if metadata.is_secured != restrict_access:
        metadata.set_secured(restrict_access)

    if restrict_access is False:
        if current_task:
            current_task.update_state(
                state=states.STARTED,
                meta={
                    "phase": "remove all allowed operations",
                }
            )
        metadata.allowed_operations.all().delete()
    if current_task:
        current_task.update_state(
            state=states.STARTED,
            meta={
                "current": AsyncResult(current_task.request.id).info.get("current", 0) + all_elements_count / 100,
                "phase": "clearing cached documents",
            }
        )

    # Clear cached documents
    ## There might be the case, that a user requests a subelements capability document just before the securing is finished
    ## In this case we would have a cached document with non-secured links and stuff - therefore we clear again in the end
    ## just to make sure!
    metadata.clear_cached_documents()

    for subelement in subelements:
        md = subelement.metadata
        if current_task:
            current_task.update_state(
                state=states.STARTED,
                meta={
                    "current": AsyncResult(current_task.request.id).info.get("current", 0) + all_elements_count / 100,
                    "phase": "clearing cached documents",
                }
            )

        if restrict_access is False:
            if current_task:
                current_task.update_state(
                    state=states.STARTED,
                    meta={
                        "phase": f"removing all allowed operations for {md.__str__()}",
                    }
                )
            md.allowed_operations.all().delete()
        # Clear cached documents
        ## There might be the case, that a user requests a subelements capability document just before the securing is finished
        ## In this case we would have a cached document with non-secured links and stuff - therefore we clear again in the end
        ## just to make sure!
        if current_task:
            current_task.update_state(
                state=states.STARTED,
                meta={
                    "phase": f"clearing cached documents for {md.__str__()}",
                }
            )
        md.clear_cached_documents()

        return {'msg': 'Done. Service secured.',
                'id': str(md.pk),
                'absolute_url': md.get_absolute_url(),
                'absolute_url_html': f'<a href={md.get_absolute_url()}>{md.title}</a>'}
