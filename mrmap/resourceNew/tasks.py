import celery.states as states
from celery import shared_task, current_task, group, chain
from resourceNew.enums.service import AuthTypeEnum
from resourceNew.models import Service as DbService
from resourceNew.models import ExternalAuthentication
from service.helper.common_connector import CommonConnector
from service.serializer.ogc.tasks import DefaultBehaviourTask
from resourceNew.parsers.capabilities import get_parsed_service, RemoteMetadata


def register_service(form: dict,
                     quantity: int = 1,
                     task_id=None,
                     **kwargs):
    # todo: chain all subtasks together
    chain(async_create_service_from_parsed_service.s(form, quantity, **kwargs),
          group(async_fetch_remote_metadata_xml.s(i, i) for i in range(100)))
    group()


@shared_task(name="async_fetch_remote_metadata_xml", base=DefaultBehaviourTask)
def async_fetch_remote_metadata_xml(remote_metadata_id):
    remote_metadata = RemoteMetadata.objects.get(pk=remote_metadata_id)
    remote_metadata.fetch_remote_content()
    return {"msg": "successfully fetched"}


@shared_task(name="async_parse_remote_metadata_xml_for_service", base=DefaultBehaviourTask)
def async_parse_remote_metadata_xml_for_service(service_id):

    remote_metadata_list = RemoteMetadata.objects.filter(service_pk=service_id)
    for remote_metadata in remote_metadata_list:
        # todo: parse the remote_metadata.content
        pass


@shared_task(name="async_create_service_from_parsed_service", base=DefaultBehaviourTask)
def async_create_service_from_parsed_service(form: dict,
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
    if current_task and task_id:
        current_task.update_state(
            state=states.STARTED,
            meta={
                'current': 0,
                'total': 100,
                'phase': 'pre configure task...',
            }
        )

    links = ""
    for _ in range(quantity):
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

        parsed_service = get_parsed_service(xml=connector.content)
        db_service = DbService.xml_objects.create_from_parsed_service(parsed_service=parsed_service)

        if external_auth:
            external_auth.secured_service = db_service
            external_auth.save()



        links += f'<a href={db_service.get_absolute_url()}>{db_service.service_metadata.title} </a>'

    result = {'msg': 'Done. New service registered.',
              'absolute_url_html': links}

    if quantity > 1:
        result.update({'msg': f'Done. {quantity} equal services registered'})
    return result
