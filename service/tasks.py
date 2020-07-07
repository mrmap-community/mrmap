"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 12.08.19

"""
import json
import time

from celery import shared_task
from django.db import transaction

from lxml.etree import XMLSyntaxError, XPathEvalError
from requests.exceptions import InvalidURL

from MrMap import utils
from MrMap.cacher import PageCacher
from MrMap.messages import SERVICE_REGISTERED, SERVICE_ACTIVATED, SERVICE_DEACTIVATED, \
    SECURITY_PROXY_MUST_BE_ENABLED_FOR_SECURED_ACCESS, SECURITY_PROXY_MUST_BE_ENABLED_FOR_LOGGING, \
    SECURITY_PROXY_DEACTIVATING_NOT_ALLOWED
from MrMap.settings import EXEC_TIME_PRINT, PROGRESS_STATUS_AFTER_PARSING
from MrMap.utils import print_debug_mode
from api.settings import API_CACHE_KEY_PREFIX
from csw.settings import CSW_CACHE_PREFIX
from service.helper.enums import MetadataEnum, OGCServiceEnum
from service.models import Service, Layer, RequestOperation, Metadata, SecuredOperation, ExternalAuthentication, \
    MetadataRelation, ProxyLog
from structure.models import MrMapUser, MrMapGroup, Organization, PendingTask

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
@transaction.atomic
def async_activate_service(metadata_id: int, user_id: int, is_active: bool):
    """ Async call for activating a service, its subelements and all of their related metadata

    Args:
        metadata_id (int): The service parameter
        user_id (int): The user id of the performing user

    Returns:
        nothing
    """
    user = MrMapUser.objects.get(id=user_id)

    # get service and change status
    service = Service.objects.get(metadata__id=metadata_id)

    elements = service.subelements + [service]
    for element in elements:
        element.is_active = is_active
        element.save(update_last_modified=False)

        md = element.metadata
        md.is_active = is_active
        md.set_documents_active_status(is_active)
        md.save(update_last_modified=False)

        # activate related metadata (if exists)
        md_relations = MetadataRelation.objects.filter(
            metadata_from=md
        )
        for relation in md_relations:
            related_md = relation.metadata_to

            # Check for dependencies before toggling active status
            # We are only interested in dependencies from activated metadatas
            relations_from_others = MetadataRelation.objects.filter(
                metadata_to=related_md,
                metadata_from__is_active=True
            )
            if relations_from_others.count() > 1 and is_active is False:
                # If there are more than our relation and we want to deactivate, we do NOT proceed
                continue
            else:
                # If there are no other dependencies OR we just want to activate the resource, we are good to go
                related_md.set_documents_active_status(is_active)
                related_md.is_active = is_active
                related_md.save()

    # Formating using an empty string here is correct, since these are the messages we show in
    # the group activity list. We reuse a message template, which uses a '{}' placeholder.
    # Since we do not show the title in here, we remove the placeholder with an empty string.
    if service.metadata.is_active:
        msg = SERVICE_ACTIVATED.format("")
    else:
        msg = SERVICE_DEACTIVATED.format("")

    # clear page cacher for API and csw
    page_cacher = PageCacher()
    page_cacher.remove_pages(API_CACHE_KEY_PREFIX)
    page_cacher.remove_pages(CSW_CACHE_PREFIX)

    user_helper.create_group_activity(service.metadata.created_by, user, msg, service.metadata.title)


@shared_task(name="async_secure_service_task")
@transaction.atomic
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
        group = MrMapGroup.objects.get(
            id=group_id
        )
    if operation_id is not None:
        operation = RequestOperation.objects.get(id=operation_id)
    else:
        operation = None

    # if whole service (wms AND wfs) shall be secured, create SecuredOperations for service object
    if md.is_metadata_type(MetadataEnum.SERVICE):
        md.service.secure_access(is_secured, group, operation, group_polygons, secured_operation)

    # secure subelements afterwards
    if md.is_metadata_type(MetadataEnum.SERVICE) or md.is_metadata_type(MetadataEnum.LAYER):
        md.service.secure_sub_elements(is_secured, group, operation, group_polygons, secured_operation)

    elif md.is_metadata_type(MetadataEnum.FEATURETYPE):
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

        print_debug_mode(EXEC_TIME_PRINT % ("total registration", time.time() - t_start))
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


@shared_task(name="async_process_secure_operations_form")
@transaction.atomic
def async_process_secure_operations_form(post_params: dict, md_id: int):
    """ Processes the secure-operations input from the access-editor form of a service.

    Args:
        post_params (dict): The dict which contains the POST parameter
        md (Metadata): The metadata object of the edited object
    Returns:
         nothing - directly changes the database
    """
    md = Metadata.objects.get(id=md_id)

    # process form input
    sec_operations_groups = json.loads(post_params.get("secured-operation-groups", "{}"))
    is_secured = post_params.get("is_secured", "")
    is_secured = is_secured == "on"  # resolve True|False

    log_proxy = post_params.get("log_proxy", "")
    log_proxy = log_proxy == "on"  # resolve True|False

    # only root metadata can toggle the use_proxy setting
    if md.is_root():
        use_proxy = post_params.get("use_proxy", "")
        # use_proxy could be None in case of subelements, which are not able to toggle the proxy option
        use_proxy = use_proxy == "on"  # resolve True|False
    else:
        use_proxy = None

    # use_proxy=False and is_secured=True and metadata.is_secured=True is not allowed!
    if use_proxy is not None:
        if not use_proxy and is_secured and md.is_secured:
            raise AssertionError(SECURITY_PROXY_MUST_BE_ENABLED_FOR_SECURED_ACCESS)

    # use_proxy=False and log_proxy=True is not allowed!
    # use_proxy=False and metadata.log_proxy_access is not allowed either!
    if not use_proxy and log_proxy:
        raise AssertionError(SECURITY_PROXY_MUST_BE_ENABLED_FOR_LOGGING)

    # raise Exception if user tries to deactivate an external authenticated service -> not allowed!
    if md.has_external_authentication() and not use_proxy:
        raise AssertionError(SECURITY_PROXY_DEACTIVATING_NOT_ALLOWED)

    # set new metadata proxy value and iterate over all children
    if use_proxy is not None and use_proxy != md.use_proxy_uri:
        md.set_proxy(use_proxy)

    # Set new log setting
    if log_proxy != md.log_proxy_access:
        md.set_logging(log_proxy)

    # set new secured value and iterate over all children
    if is_secured != md.is_secured:
        md.set_secured(is_secured)

    # If service is not secured (anymore), we have to remove all SecuredOperation records related to this metadata
    if not is_secured:
        # remove all secured settings
        sec_ops = SecuredOperation.objects.filter(
            secured_metadata=md
        )
        sec_ops.delete()

        # remove all secured settings for subelements
        async_secure_service_task(md.id, is_secured, None, None, None, None)

    else:
        # Create securing tasks for each group to speed up process
        for item in sec_operations_groups:
            group_items = item.get("groups", {})
            for group_item in group_items:
                item_sec_op_id = int(group_item.get("securedOperation", "-1"))
                group_id = int(group_item.get("groupId", "-1"))
                remove = group_item.get("remove", "false")
                remove = utils.resolve_boolean_attribute_val(remove)
                group_polygons = group_item.get("polygons", "{}")
                group_polygons = utils.resolve_none_string(group_polygons)
                if group_polygons is not None:
                    group_polygons = json.loads(group_polygons)
                else:
                    group_polygons = []

                operation = item.get("operation", None)

                if remove:
                    # remove this secured operation
                    sec_op = SecuredOperation.objects.get(
                        id=item_sec_op_id
                    )
                    sec_op.delete()
                else:
                    operation = RequestOperation.objects.get(
                        operation_name=operation
                    )
                    if item_sec_op_id == -1:
                        # create new setting
                        async_secure_service_task(md.id, is_secured, group_id, operation.id, group_polygons, None)
                    else:
                        # edit existing one
                        async_secure_service_task(md.id, is_secured, group_id, operation.id, group_polygons, item_sec_op_id)

    # Clear cached documents
    ## There might be the case, that a user requests a subelements capability document just before the securing is finished
    ## In this case we would have a cached document with non-secured links and stuff - therefore we clear again in the end
    ## just to make sure!
    md.clear_cached_documents()
    sub_mds = md.get_subelements_metadatas()
    for sub_md in sub_mds:
        sub_md.clear_cached_documents()
