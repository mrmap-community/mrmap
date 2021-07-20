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
from MrMap.settings import EXEC_TIME_PRINT
from service.helper.common_connector import CommonConnector
from service.helper.enums import ConnectionEnum
from service.serializer.ogc.factory.factorys import OGCServiceFactory
from main.tasks import DefaultBehaviourTask
from service.models import Metadata, ExternalAuthentication, ProxyLog
from service.settings import PROGRESS_STATUS_AFTER_PARSING
from structure.models import Organization
from service.helper import service_helper
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


@shared_task(name="resolve_linked_iso_md")
def get_linked_iso_metadata(uri):
    ows_connector = CommonConnector(
        url=uri,
        external_auth=None,
        connection_type=ConnectionEnum.REQUESTS
    )
    ows_connector.http_method = 'GET'
    ows_connector.load()
    if ows_connector.status_code == 200:
        return {'uri': uri,
                'response': ows_connector.content.decode("UTF-8")}
    else:
        return {'uri': uri,
                'response': ''}


@shared_task(name="async_new_service_task", base=DefaultBehaviourTask)
def async_new_service(owned_by_org: str,
                      url_dict: dict,
                      external_auth: dict,
                      quantity: int = 1,
                      **kwargs):
    """ Async call of new service creation

    Since redis is used as broker, the objects can not be passed directly into the function. They have to be resolved using
    their ids, since the objects are not easily serializable using json

    Args:
        owned_by_org (str): pk of the organization which shall own this service
        url_dict (dict): Contains basic information about the service like connection uri
        external_auth (dict): ExternalAuthentication object as dict
        quantity (int): how many services from this url are registered in one process. Default is 1. Only used for
                        developing purposes.
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
    url_dict["service"] = service_helper.resolve_service_enum(url_dict["service"])
    url_dict["version"] = service_helper.resolve_version_enum(url_dict["version"])

    register_for_organization = Organization.objects.get(pk=owned_by_org)

    t_start = time.time()

    service = OGCServiceFactory.get_service_instance(service_type=url_dict.get("service"),
                                                     version=url_dict.get("version"),
                                                     service_connect_url=url_dict.get("base_uri"),
                                                     external_auth=external_auth)

    service.parse()

    if current_task:
        current_task.update_state(
            state=states.STARTED,
            meta={
                'current': PROGRESS_STATUS_AFTER_PARSING,
                'phase': 'Persisting...',
            }
        )
    links = ''
    for x in range(quantity):
        service_db_instance = service.to_db(
            register_for_organization,
            None
        )
        if external_auth is not None:
            #todo: check this......
            if current_task:
                current_task.update_state(
                    state=states.STARTED,
                    meta={
                        'current': PROGRESS_STATUS_AFTER_PARSING,
                        'phase': 'Securing...',
                        'service': service_db_instance.metadata.title
                    }
                )
            service_db_instance.metadata.set_proxy(True)

        links += f'<a href={service_db_instance.metadata.get_absolute_url()}>{service_db_instance.metadata.title} </a>'

    settings.ROOT_LOGGER.debug(EXEC_TIME_PRINT % ("total registration", time.time() - t_start))

    result = {'msg': 'Done. New service registered.',
              #'id': str(service.metadata.pk),
              #'absolute_url': service.metadata.get_absolute_url(),
              'absolute_url_html': links}

    if quantity > 1:
        result.update({'msg': f'Done. {quantity} equal services registered'})
    return result


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
