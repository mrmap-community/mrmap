import celery.states as states
from celery import shared_task, current_task, group, chain, chord
from resourceNew.enums.service import AuthTypeEnum
from resourceNew.models import Service as DbService
from resourceNew.models import ExternalAuthentication, RemoteMetadata
from service.helper.common_connector import CommonConnector
from service.serializer.ogc.tasks import DefaultBehaviourTask
from resourceNew.parsers.capabilities import get_parsed_service
from django.conf import settings
from service.settings import service_logger


@shared_task(name="async_get_linked_metadata", base=DefaultBehaviourTask)
def get_linked_metadata(service_id,
                        **kwargs):
    remote_metadata_list = RemoteMetadata.objects.filter(service__pk=service_id)
    header = [fetch_remote_metadata_xml.s(remote_metadata.pk, **kwargs) for remote_metadata in remote_metadata_list]
    callback = parse_remote_metadata_xml_for_service.s(service_id, **kwargs)
    task = chord(header)(callback)
    return task


@shared_task(name="async_fetch_remote_metadata_xml", base=DefaultBehaviourTask)
def fetch_remote_metadata_xml(remote_metadata_id,
                              **kwargs):
    remote_metadata = RemoteMetadata.objects.get(pk=remote_metadata_id)
    try:
        remote_metadata.fetch_remote_content()
    except Exception as e:
        service_logger.exception(e, stack_info=True, exc_info=True)
        # todo: log exception in debug level
    return {"msg": "successfully done", "remote_metadata_id": remote_metadata.id}


@shared_task(name="async_parse_remote_metadata_xml_for_service", base=DefaultBehaviourTask)
def parse_remote_metadata_xml_for_service(remote_metadata_ids,
                                          service_id,
                                          **kwargs):
    # todo: remote_metadata_ids is a list of None values...
    remote_metadata_list = RemoteMetadata.objects.filter(service__pk=service_id)
    for remote_metadata in remote_metadata_list:
        try:
            remote_metadata.create_metadata_instance()
        except Exception as e:
            service_logger.exception(e, stack_info=True, exc_info=True)
            # todo: log exception in debug level
    return {"msg": "successfully done"}


@shared_task(name="async_create_service_from_parsed_service", base=DefaultBehaviourTask)
def create_service_from_parsed_service(form: dict,
                                       quantity: int = 1,
                                       task_id=None,
                                       **kwargs):
    """ Async call of new service creation

    Since redis is used as broker, the objects can not be passed directly into the function. They have to be resolved using
    their ids, since the objects are not easily serializable using json

    Args:
        form (dict): the cleaned_data dict of the used RegisterServiceForm
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
                'phase': 'download capabilities document...',
            }
        )
    if form["auth_type"] != AuthTypeEnum.NONE.value:
        external_auth = ExternalAuthentication(
            username=form["username"],
            password=form["password"],
            auth_type=form["auth_type"],
        )
    else:
        external_auth = None
    connector = CommonConnector(url=form["test_url"], external_auth=external_auth)
    connector.load()

    if current_task:
        current_task.update_state(
            state=states.STARTED,
            meta={
                'current': 0,
                'total': 100,
                'phase': 'parse capabilities document...',
            }
        )
    parsed_service = get_parsed_service(xml=connector.content)

    links = ""
    sub_tasks = []
    for _ in range(quantity):
        if current_task:
            current_task.update_state(
                state=states.STARTED,
                meta={
                    'current': 0,
                    'total': 100,
                    'phase': 'register service...',
                }
            )
        db_service = DbService.xml_objects.create_from_parsed_service(parsed_service=parsed_service)

        if external_auth:
            external_auth.secured_service = db_service
            external_auth.save()

        if form.get("collect_linked_metadata", False):
            task = get_linked_metadata.apply_async((db_service.pk, ),
                                                   kwargs=kwargs,
                                                   countdown=settings.CELERY_DEFAULT_COUNTDOWN)
            if current_task:
                current_task.update_state(
                    state=states.STARTED,
                    meta={
                        'current': 0,
                        'total': 100,
                        'phase': 'start collect metadata task...',
                    }
                )
            sub_tasks.append(task)
        links += f'<a href={db_service.get_absolute_url()}>{db_service.metadata.title} </a>'

    result = {'msg': 'Done. New service registered.',
              'subtasks': [task.task_id for task in sub_tasks],
              'absolute_url_html': links}

    if quantity > 1:
        result.update({'msg': f'Done. {quantity} equal services registered'})
    return result
