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

import requests
from celery import shared_task
from django.contrib.gis.geos import GEOSGeometry, Polygon, GeometryCollection
from django.db import transaction

from lxml.etree import XMLSyntaxError, XPathEvalError
from requests.exceptions import InvalidURL

from MrMap import utils
from MrMap.cacher import PageCacher
from MrMap.messages import SERVICE_REGISTERED, SERVICE_ACTIVATED, SERVICE_DEACTIVATED
from MrMap.settings import EXEC_TIME_PRINT
from api.settings import API_CACHE_KEY_PREFIX
from csw.settings import CSW_CACHE_PREFIX
from service.settings import DEFAULT_SRS
from service.models import Service, Metadata, SecuredOperation, ExternalAuthentication, \
    MetadataRelation, ProxyLog
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


@shared_task(name="async_activate_service")
@transaction.atomic
def async_activate_service(metadata_id, user_id: int, is_active: bool):
    """ Async call for activating a service, its subelements and all of their related metadata

    Args:
        metadata_id : The service parameter
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
        md_relations = md.related_metadata.all()
        for relation in md_relations:
            related_md = relation.metadata_to

            # Check for dependencies before toggling active status
            # We are only interested in dependencies from activated metadatas
            relations_from_others = MetadataRelation.objects.filter(
                metadata_to=related_md,
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
        msg = SERVICE_ACTIVATED
    else:
        msg = SERVICE_DEACTIVATED

    # clear page cacher for API and csw
    page_cacher = PageCacher()
    page_cacher.remove_pages(API_CACHE_KEY_PREFIX)
    page_cacher.remove_pages(CSW_CACHE_PREFIX)

    user_helper.create_group_activity(service.metadata.created_by, user, msg, service.metadata.title)


@shared_task(name="async_secure_service_task")
def async_secure_service_task(metadata_id: int, group_id: int, operations: list, bounding_geometry: str):
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

    # First get the MrMapGroup object
    if group_id is None:
        group = None
    else:
        group = MrMapGroup.objects.get(
            id=group_id
        )

    try:
        features = json.loads(bounding_geometry)
        geoms = []
        for feature in features["features"]:
            feature_geom = feature["geometry"]
            feature_coords = feature_geom["coordinates"]
            for coord in feature_coords:
                geom = GEOSGeometry(Polygon(coord), srid=DEFAULT_SRS)
                geoms.append(geom)
        # Create GeosGeometry from GeoJson
        bounding_geometry = GeometryCollection(
            geoms
        )
    except Exception as e:
        bounding_geometry = None

    # Create list of parent metadata and all subelement metadatas
    metadatas = md.get_subelements_metadatas()
    metadatas = [md] + metadatas

    with transaction.atomic():
        # Iterate over all metadatas to set the restricted geometry
        for md in metadatas:
            # Create a list of objects, which shall be deleted if not found anymore in the new form data
            to_be_deleted = md.secured_operations.filter(
                allowed_group=group
            )
            to_be_deleted = {op.operation: op for op in to_be_deleted}
            # Then iterate over all operations, which shall be secured and create/update the bounding geometry
            for operation in operations:
                try:
                    # Since we are currently iterating through this operation, which shall be secured, we can delete
                    # the entry from the list of entries which would be deleted in the end!
                    del to_be_deleted[operation]
                except KeyError:
                    pass
                secured_operation = md.secured_operations.filter(
                    operation=operation,
                    allowed_group=group,
                )
                if secured_operation.exists():
                    # update
                    secured_operation = secured_operation.first()
                    secured_operation.bounding_geometry = bounding_geometry
                    secured_operation.save()
                else:
                    # New!
                    sec_op = SecuredOperation.objects.create(
                        secured_metadata=md,
                        operation=operation,
                        allowed_group=group,
                        bounding_geometry=bounding_geometry
                    )
                    md.secured_operations.add(sec_op)

            # Delete the operations which are not present anymore in the form data!
            for key, entry in to_be_deleted.items():
                entry.delete()


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
        sub_metadatas = service.metadata.get_subelements_metadatas()
        dataset_metadatas = list(filter(None, [md.get_related_dataset_metadata() for md in sub_metadatas]))
        metadatas = [service.metadata] + sub_metadatas + dataset_metadatas
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
