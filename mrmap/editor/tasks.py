"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 29.07.20

"""
import json

from celery import shared_task

from service.helper import task_helper
from service.helper.enums import PendingTaskEnum
from service.helper.task_helper import update_progress_by_step
from service.models import Metadata
from structure.models import PendingTask


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

    # get current task id
    curr_task_id = async_process_securing_access.request.id

    # create db object, so we know which pending task is still ongoing
    pending_task_db = PendingTask.objects.create(
        task_id=curr_task_id,
        description=json.dumps({
            "service": metadata.__str__(),
            "phase": "collecting sub elements of the service",
        }),
        type=PendingTaskEnum.SECURE.value
    )

    task_helper.update_progress(async_process_securing_access, 0)

    # Create list of main and sub metadatas for later use
    subelements = metadata.get_described_element()\
                          .get_subelements()\
                          .select_related('metadata')\
                          .prefetch_related('metadata__documents')  # could be list of layers or featuretypes
    all_elements_count = len(subelements) + 1

    pending_task_db.description = json.dumps({
            "service": metadata.__str__(),
            "phase": "update use proxy setting of service elements",
        })
    pending_task_db.save()
    if metadata.use_proxy_uri != use_proxy:
        metadata.set_proxy(use_proxy)

    pending_task_db.description = json.dumps({
        "service": metadata.__str__(),
        "phase": "update log proxy access setting of service elements",
    })
    pending_task_db.save()
    if metadata.log_proxy_access != log_proxy:
        metadata.set_logging(log_proxy)

    pending_task_db.description = json.dumps({
        "service": metadata.__str__(),
        "phase": "update secure flag of service elements",
    })
    pending_task_db.save()
    if metadata.is_secured != restrict_access:
        metadata.set_secured(restrict_access)

    if restrict_access is False:
        pending_task_db.description = json.dumps({
            "service": metadata.__str__(),
            "phase": "remove all allowed operations",
        })
        pending_task_db.save()
        metadata.allowed_operations.all().delete()

    pending_task_db.description = json.dumps({
        "service": metadata.__str__(),
        "phase": "clearing cached documents",
    })
    pending_task_db.save()
    update_progress_by_step(task=async_process_securing_access, step=all_elements_count/100)

    # Clear cached documents
    ## There might be the case, that a user requests a subelements capability document just before the securing is finished
    ## In this case we would have a cached document with non-secured links and stuff - therefore we clear again in the end
    ## just to make sure!
    metadata.clear_cached_documents()

    for subelement in subelements:
        md = subelement.metadata
        update_progress_by_step(task=async_process_securing_access, step=all_elements_count/100)

        if restrict_access is False:
            pending_task_db.description = json.dumps({
                "service": metadata.__str__(),
                "phase": f"removing all allowed operations for {md.__str__()}",
            })
            pending_task_db.save()
            md.allowed_operations.all().delete()
        # Clear cached documents
        ## There might be the case, that a user requests a subelements capability document just before the securing is finished
        ## In this case we would have a cached document with non-secured links and stuff - therefore we clear again in the end
        ## just to make sure!
        pending_task_db.description = json.dumps({
            "service": metadata.__str__(),
            "phase": f"clearing cached documents for {md.__str__()}",
        })
        pending_task_db.save()
        md.clear_cached_documents()

    task_helper.update_progress(async_process_securing_access, 100)
    pending_task_db.is_finished = True
    pending_task_db.save()
