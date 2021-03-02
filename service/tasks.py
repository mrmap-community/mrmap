"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 12.08.19

"""
import base64
import json
import time
import traceback
from requests.exceptions import InvalidURL

import requests
from celery import shared_task
from django.contrib.gis.geos import MultiPolygon
from django.db import transaction
from lxml.etree import XMLSyntaxError, XPathEvalError

from MrMap import utils
from MrMap.cacher import PageCacher
from MrMap.messages import SERVICE_REGISTERED, SERVICE_ACTIVATED, SERVICE_DEACTIVATED
from MrMap.settings import EXEC_TIME_PRINT
from api.settings import API_CACHE_KEY_PREFIX
from csw.settings import CSW_CACHE_PREFIX
from service.models import Service, Metadata, ExternalAuthentication, ProxyLog, AllowedOperation, OGCOperation
from service.settings import service_logger, PROGRESS_STATUS_AFTER_PARSING
from structure.models import MrMapUser, MrMapGroup, Organization, PendingTask, ErrorReport
from service.helper import service_helper, task_helper
from users.helper import user_helper


@shared_task(name="async_increase_hits")
def async_increase_hits(metadata_id: int):
    """ Async call for increasing the hit counter of a metadata record

    Args:
        metadata_id (int): The metadata record id
    Returns:
         nothing
    """
    md = Metadata.objects.get(id=metadata_id)
    md.increase_hits()


# todo: maybe we don't need this function after SecuredOperation is refactored
#  tag: delete
@shared_task(name="async_secure_service_task")
def async_secure_service_task(root_metadata_id: int,
                              groups_id_list: list,
                              operations_id_list: list,
                              allowed_area: str):
    """ Async call for securing a service

    Since this is something that can happen in the background, we should push it to the background!

    Args;
        metadata_id (int): The service that shall be secured
        is_secured (bool): Whether to secure the service or not
        groups (list): The groups which are allowed to perform the RequestOperation
        operation (RequestOperation): The operation that shall be secured or not
    Returns:
         nothing
    """
    root_metadata = Metadata.objects.get(id=root_metadata_id)
    allowed_groups = MrMapGroup.objects.filter(
        id__in=groups_id_list
    )
    operations = OGCOperation.objects.filter(
        id__in=operations_id_list
    )
    allowed_area = MultiPolygon(allowed_area)

    obj, created = AllowedOperation.objects.get_or_create(
        root_metadata=root_metadata,
    )
    obj.allowed_groups.clear()
    obj.operations.clear()
    obj.allowed_groups.add(*allowed_groups)
    obj.operations.add(*operations)
    obj.allowed_area = allowed_area

    obj.save()


@shared_task(name="async_remove_service_task")
def async_remove_service_task(service_id: int):
    """ Async call for removing of services

    Since this is something that can happen in the background, we should push it to the background!

    Args;
        service_id (int): The id of the service which shall be removed
    Returns:
         nothing
    """
    service = Service.objects.get(id=service_id)
    service.delete()


@shared_task(name="async_new_service_task")
def async_new_service(url_dict: dict, user_id: int, register_group_id: int, register_for_organization_id: int,
                      external_auth: dict):
    """ Async call of new service creation

    Since redis is used as broker, the objects can not be passed directly into the function. They have to be resolved using
    their ids, since the objects are not easily serializable using json

    Args:
        url_dict (dict): Contains basic information about the service like connection uri
        user_id (int): Id of the performing user
        register_group_id (int): Id of the group which wants to register
        register_for_organization_id (int): Id of the organization for which the service is registered
    Returns:
        nothing
    """
    # create ExternalAuthentication object
    if external_auth is not None:
        external_auth = ExternalAuthentication(
            username=external_auth["username"],
            password=external_auth["password"],
            auth_type=external_auth["auth_type"],
        )

    # get current task id
    curr_task_id = async_new_service.request.id

    # set progress for current task to 0
    if curr_task_id is not None:
        task_helper.update_progress(async_new_service, 0)

    # restore objects from ids
    user = MrMapUser.objects.get(id=user_id)
    url_dict["service"] = service_helper.resolve_service_enum(url_dict["service"])
    url_dict["version"] = service_helper.resolve_version_enum(url_dict["version"])

    register_group = MrMapGroup.objects.get(id=register_group_id)
    if utils.resolve_none_string(str(register_for_organization_id)) is not None:
        register_for_organization = Organization.objects.get(id=register_for_organization_id)
    else:
        register_for_organization = None

    try:
        t_start = time.time()
        service = service_helper.create_service(
            url_dict.get("service"),
            url_dict.get("version"),
            url_dict.get("base_uri"),
            user,
            register_group,
            register_for_organization,
            async_task=async_new_service,
            external_auth=external_auth
        )

        # update progress
        if curr_task_id is not None:
            task_helper.update_progress(async_new_service, PROGRESS_STATUS_AFTER_PARSING)

        # get db object
        if curr_task_id is not None:
            pending_task = PendingTask.objects.get(task_id=curr_task_id)
            # update db pending task information
            pending_task.description = json.dumps({
                "service": service.metadata.title,
                "phase": "Persisting",
            })
            pending_task.save()

        # update progress
        if curr_task_id is not None:
            task_helper.update_progress(async_new_service, 95)

        # after service AND documents have been persisted, we can now set the service being secured if needed
        if external_auth is not None:
            service.metadata.set_proxy(True)

        # after metadata has been persisted, we can auto-generate all metadata public_id's
        metadatas = Metadata.objects.filter(pk=service.metadata.pk)
        sub_elements = service.get_subelements().select_related('metadata')
        for sub_element in sub_elements:
            metadatas |= Metadata.objects.filter(pk=sub_element.metadata.pk)
            metadatas |= sub_element.metadata.get_related_dataset_metadatas()

        for md in metadatas:
            if md.public_id is None:
                md.public_id = md.generate_public_id()
                md.save()
        service_logger.debug(EXEC_TIME_PRINT % ("total registration", time.time() - t_start))
        user_helper.create_group_activity(service.metadata.created_by, user, SERVICE_REGISTERED, service.metadata.title)

        if curr_task_id is not None:
            task_helper.update_progress(async_new_service, 100)

        # delete pending task from db
        if curr_task_id is not None:
            pending_task = PendingTask.objects.get(task_id=curr_task_id)
            pending_task.delete()

    except (BaseException, XMLSyntaxError, XPathEvalError, InvalidURL, ConnectionError) as e:
        url = url_dict['base_uri'] + f"SERVICE={url_dict['service'].value}&VERSION={url_dict['version'].value}&request={url_dict['request']}"
        error_msg = f"Error while trying to register new resource for url: {url}\n"

        response = requests.get(url)
        if response.status_code == 200:
            cap_doc = "-----------------------------------------------------------\n"\
                      f"We could receive the following capabilities document:\n{response.text}"
            error_msg += cap_doc

        service_logger.error(msg=error_msg)
        service_logger.exception(e, stack_info=True, exc_info=True)

        if curr_task_id is not None:
            pending_task = PendingTask.objects.get(task_id=curr_task_id)

            register_group = MrMapGroup.objects.get(id=register_group_id)
            error_report = ErrorReport(message=error_msg,
                                       traceback=traceback.format_exc(),
                                       created_by=register_group)
            error_report.save()

            descr = json.loads(pending_task.description)
            pending_task.description = json.dumps({
                "service": descr.get("service", None),
                "info": {
                    "current": "0",
                },
                "exception": e.__str__(),
                "phase": "ERROR: Something went wrong! Click on generate error report to inform your serveradmin about this error.",
            })
            pending_task.error_report = error_report
            pending_task.save()

        raise e


@shared_task(name="async_log_response")
def async_log_response(proxy_log_id: int, response: str, request_param: str, format_param: str):
    response = base64.b64decode(response.encode("UTF-8"))
    proxy_log = ProxyLog.objects.get(
        id=proxy_log_id
    )
    proxy_log.log_response(
        response,
        request_param,
        format_param
    )
