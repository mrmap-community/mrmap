"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 12.08.19

"""
import json
import time

from celery import shared_task

from lxml.etree import XMLSyntaxError, XPathEvalError
from requests.exceptions import InvalidURL

from MapSkinner import utils
from MapSkinner.messages import SERVICE_REGISTERED
from MapSkinner.settings import EXEC_TIME_PRINT
from structure.models import User, Group, Organization, PendingTask

from service.helper import service_helper
from users.helper import user_helper


@shared_task(name="async_new_service_task")
def async_new_service(url_dict: dict, user_id: int, register_group_id: int, register_for_organization_id: int):
    """ Async call of new service creation

    Since redis is used as broker, the objects can not be passed directly into the function. They have to be resolved using
    their ids, since the objects are not easily serializable using json

    :param url_dict:
    :param user_id:
    :param register_group_id:
    :param register_for_organization_id:
    :return:
    """
    # get current task id
    curr_task_id = async_new_service.request.id

    # set progress for current task to 0
    async_new_service.update_state(state='PROGRESS',
                           meta={'current': 0,'total': 100,}
                           )
    # restore objects from ids
    user = User.objects.get(id=user_id)
    url_dict["service"] = service_helper.resolve_service_enum(url_dict["service"])
    url_dict["version"] = service_helper.resolve_version_enum(url_dict["version"])

    register_group = Group.objects.get(id=register_group_id)
    if utils.resolve_none_string(register_for_organization_id) is not None:
        register_for_organization = Organization.objects.get(id=register_for_organization_id)
    else:
        register_for_organization = None

    try:
        async_new_service.update_state(state='PROGRESS',
                                       meta={
                                           'current': 10,
                                           'total': 100,
                                       }
                                       )
        t_start = time.time()
        service = service_helper.get_service_model_instance(
            url_dict.get("service"),
            url_dict.get("version"),
            url_dict.get("base_uri"),
            user,
            register_group,
            register_for_organization
        )
        async_new_service.update_state(state='PROGRESS',
                                       meta={
                                           'current': 65,
                                           'total': 100,
                                       }
                                       )

        # get return values
        raw_service = service["raw_data"]
        service = service["service"]

        # get db object
        pending_task = PendingTask.objects.get(task_id=curr_task_id)
        # update db pending task information
        pending_task.description = json.dumps({
            "service": service.metadata.title,
            "phase": "persisting",
        })
        pending_task.save()

        xml = raw_service.service_capabilities_xml

        # persist everything
        service_helper.persist_service_model_instance(service)
        async_new_service.update_state(state='PROGRESS',
                                       meta={
                                           'current': 90,
                                           'total': 100,
                                       }
                                       )
        service_helper.persist_capabilities_doc(service, xml)

        #params["service"] = raw_service
        print(EXEC_TIME_PRINT % ("total registration", time.time() - t_start))
        user_helper.create_group_activity(service.metadata.created_by, user, SERVICE_REGISTERED, service.metadata.title)
        async_new_service.update_state(state='PROGRESS',
                                       meta={
                                           'current': 100,
                                           'total': 100,
                                       }
                                       )

        # delete pending task from db
        pending_task = PendingTask.objects.get(task_id=curr_task_id)
        pending_task.delete()
    except (ConnectionError, InvalidURL) as e:
        #params["error"] = e.args[0]
        raise e
    except (BaseException, XMLSyntaxError, XPathEvalError) as e:
        #params["unknown_error"] = e
        raise e