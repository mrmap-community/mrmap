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
from MapSkinner.messages import SERVICE_REGISTERED, SERVICE_ACTIVATED, SERVICE_DEACTIVATED
from MapSkinner.settings import EXEC_TIME_PRINT, PROGRESS_STATUS_AFTER_PARSING
from service.helper.enums import MetadataEnum, ServiceEnum
from service.models import Service, Layer, RequestOperation, Metadata, SecuredOperation, ExternalAuthentication
from structure.models import User, Group, Organization, PendingTask

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


@shared_task(name="async_activate_service")
def async_activate_service(service_id: int, user_id: int):
    """ Async call for activating a service, its subelements and all of their related metadata

    Args:
        service_id (int): The service parameter
        user_id (int): The user id of the performing user
    Returns:
        nothing
    """
    user = User.objects.get(id=user_id)

    # get service and change status
    service = Service.objects.get(id=service_id)
    new_status = not service.metadata.is_active  # invert active status
    service.metadata.is_active = new_status
    service.metadata.save(update_last_modified=False)
    service.is_active = new_status
    service.save(update_last_modified=False)

    # get root_layer of service and start changing of all statuses
    # also check all related metadata and activate them too
    if service.servicetype.name == ServiceEnum.WMS.value:
        service.activate_service(new_status)
        root_layer = Layer.objects.get(parent_service=service, parent_layer=None)
        root_layer.activate_layer_recursive(new_status)

    if service.metadata.is_active:
        msg = SERVICE_ACTIVATED
    else:
        msg = SERVICE_DEACTIVATED

    user_helper.create_group_activity(service.metadata.created_by, user, msg, service.metadata.title)


@shared_task(name="async_secure_service_task")
def async_secure_service_task(metadata_id: int, is_secured: bool, group_id: int, operation_id: int, group_polygons: dict, secured_operation_id: int):
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
    md = Metadata.objects.get(id=metadata_id)
    if secured_operation_id is not None:
        secured_operation = SecuredOperation.objects.get(
            id=secured_operation_id
        )
    else:
        secured_operation = None
    if group_id is None:
        group = None
    else:
        group = Group.objects.get(
            id=group_id
        )
    if operation_id is not None:
        operation = RequestOperation.objects.get(id=operation_id)
    else:
        operation = None

    md_type = md.metadata_type.type

    # if whole service (wms AND wfs) shall be secured, create SecuredOperations for service object
    if md_type == MetadataEnum.SERVICE.value:
        md.service.perform_single_element_securing(md.service, is_secured, group, operation, group_polygons, secured_operation)

    # secure subelements afterwards
    if md_type == MetadataEnum.SERVICE.value or md_type == MetadataEnum.LAYER.value:
        md.service.secure_sub_elements(is_secured, group, operation, group_polygons, secured_operation)

    elif md_type == MetadataEnum.FEATURETYPE.value:
        md.featuretype.secure_feature_type(is_secured, group, operation, group_polygons, secured_operation)


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
def async_new_service(url_dict: dict, user_id: int, register_group_id: int, register_for_organization_id: int, external_auth: dict):
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
    user = User.objects.get(id=user_id)
    url_dict["service"] = service_helper.resolve_service_enum(url_dict["service"])
    url_dict["version"] = service_helper.resolve_version_enum(url_dict["version"])

    register_group = Group.objects.get(id=register_group_id)
    if utils.resolve_none_string(register_for_organization_id) is not None:
        register_for_organization = Organization.objects.get(id=register_for_organization_id)
    else:
        register_for_organization = None

    try:
        t_start = time.time()
        service = service_helper.get_service_model_instance(
            url_dict.get("service"),
            url_dict.get("version"),
            url_dict.get("base_uri"),
            user,
            register_group,
            register_for_organization,
            async_task=async_new_service,
            external_auth=external_auth
        )

        ## update progress
        if curr_task_id is not None:
            task_helper.update_progress(async_new_service, PROGRESS_STATUS_AFTER_PARSING)

        # get return values
        raw_service = service["raw_data"]
        service = service["service"]

        # get db object
        if curr_task_id is not None:
            pending_task = PendingTask.objects.get(task_id=curr_task_id)
            # update db pending task information
            pending_task.description = json.dumps({
                "service": service.metadata.title,
                "phase": "Persisting",
            })
            pending_task.save()

        xml = raw_service.service_capabilities_xml

        # persist everything
        service_helper.persist_service_model_instance(service, external_auth)

        # update progress
        if curr_task_id is not None:
            task_helper.update_progress(async_new_service, 95)

        service.persist_capabilities_doc(xml)

        # after service AND documents have been persisted, we can now set the service being secured
        if external_auth is not None:
            service.metadata.set_secured(True)

        print(EXEC_TIME_PRINT % ("total registration", time.time() - t_start))
        user_helper.create_group_activity(service.metadata.created_by, user, SERVICE_REGISTERED, service.metadata.title)

        if curr_task_id is not None:
            task_helper.update_progress(async_new_service, 100)

        # delete pending task from db
        if curr_task_id is not None:
            pending_task = PendingTask.objects.get(task_id=curr_task_id)
            pending_task.delete()

    except (BaseException, XMLSyntaxError, XPathEvalError, InvalidURL, ConnectionError) as e:
        if curr_task_id is not None:
            pending_task = PendingTask.objects.get(task_id=curr_task_id)
            descr = json.loads(pending_task.description)
            pending_task.description = json.dumps({
                "service": descr.get("service", None),
                "info": {
                    "current": "0",
                },
                "exception": e.__str__(),
            })
            pending_task.save()
        raise e