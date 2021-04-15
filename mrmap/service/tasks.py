"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 12.08.19

"""
import base64
import json
import time

import celery.states as states
from celery import shared_task, current_task
from MrMap import utils
from MrMap.messages import SERVICE_REGISTERED
from MrMap.settings import EXEC_TIME_PRINT
from service.models import Metadata, ExternalAuthentication, ProxyLog
from service.settings import service_logger, PROGRESS_STATUS_AFTER_PARSING
from structure.models import MrMapUser, MrMapGroup, Organization
from service.helper import service_helper
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


@shared_task(name="async_new_service_task")
def async_new_service(url_dict: dict,
                      user_id: int,
                      register_group_id: int,
                      register_for_organization_id: int,
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
    if current_task:
        current_task.update_state(
            state=states.STARTED,
            meta={
                'current': 0,
                'total': 100,
                'phase': 'pre configure task...',
            }
        )

    # create ExternalAuthentication object
    if external_auth is not None:
        external_auth = ExternalAuthentication(
            username=external_auth["username"],
            password=external_auth["password"],
            auth_type=external_auth["auth_type"],
        )

    # restore objects from ids
    user = MrMapUser.objects.get(id=user_id)
    url_dict["service"] = service_helper.resolve_service_enum(url_dict["service"])
    url_dict["version"] = service_helper.resolve_version_enum(url_dict["version"])

    register_group = MrMapGroup.objects.get(id=register_group_id)
    if utils.resolve_none_string(str(register_for_organization_id)) is not None:
        register_for_organization = Organization.objects.get(id=register_for_organization_id)
    else:
        register_for_organization = None

    t_start = time.time()
    service = service_helper.create_service(
        url_dict.get("service"),
        url_dict.get("version"),
        url_dict.get("base_uri"),
        user,
        register_group,
        register_for_organization,
        external_auth=external_auth
    )

    # after service AND documents have been persisted, we can now set the service being secured if needed
    if external_auth is not None:
        #todo: check this......
        if current_task:
            current_task.update_state(
                state=states.STARTED,
                meta={
                    'current': PROGRESS_STATUS_AFTER_PARSING,
                    'phase': 'Securing...',
                    'service': service.metadata.title
                }
            )
        service.metadata.set_proxy(True)

    service_logger.debug(EXEC_TIME_PRINT % ("total registration", time.time() - t_start))
    user_helper.create_group_activity(service.metadata.created_by, user, SERVICE_REGISTERED, service.metadata.title)

    return {'msg': 'Done. New service registered.',
            'id': str(service.metadata.pk),
            'absolute_url': service.metadata.get_absolute_url(),
            'absolute_url_html': f'<a href={service.metadata.get_absolute_url()}>{service.metadata.title}</a>'}


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
