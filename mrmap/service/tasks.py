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

from django.contrib.auth import get_user_model
from requests.exceptions import InvalidURL

import requests
from celery import shared_task
from lxml.etree import XMLSyntaxError, XPathEvalError
from MrMap.settings import EXEC_TIME_PRINT
from service.models import Metadata, ExternalAuthentication, ProxyLog
from service.settings import service_logger, PROGRESS_STATUS_AFTER_PARSING
from structure.models import Organization, PendingTask, ErrorReport
from service.helper import task_helper
from mrmap.service.helper import service_helper
from django.conf import settings


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


@shared_task(name="async_new_service_task")
def async_new_service(url_dict: dict, user_id: int, register_for_organization_id: int,
                      external_auth: dict):
    """ Async call of new service creation

    Since redis is used as broker, the objects can not be passed directly into the function. They have to be resolved using
    their ids, since the objects are not easily serializable using json

    Args:
        url_dict (dict): Contains basic information about the service like connection uri
        user_id (int): Id of the performing user
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
    user = get_user_model().objects.get(id=user_id)
    url_dict["service"] = service_helper.resolve_service_enum(url_dict["service"])
    url_dict["version"] = service_helper.resolve_version_enum(url_dict["version"])

    register_for_organization = Organization.objects.get(pk=register_for_organization_id)

    try:
        t_start = time.time()
        service = service_helper.create_service(
            url_dict.get("service"),
            url_dict.get("version"),
            url_dict.get("base_uri"),
            user,
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

        service_logger.debug(EXEC_TIME_PRINT % ("total registration", time.time() - t_start))

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

            register_org = Organization.objects.get(id=register_for_organization_id)
            error_report = ErrorReport(message=error_msg,
                                       traceback=traceback.format_exc(),
                                       created_by=register_org)
            error_report.save()

            descr = json.loads(pending_task.description)
            pending_task.description = json.dumps({
                "service": descr.get("service", None),
                "info": {
                    "current": "0",
                },
                "exception": e.__str__(),
                "phase": "ERROR: Something went wrong! Click on generate error report to inform your serveradmin "
                         "about this error.",
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
