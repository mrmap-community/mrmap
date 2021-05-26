import celery.states as states
from celery import shared_task, current_task
from resourceNew.enums.service import AuthTypeEnum
from resourceNew.models import Service as DbService
from resourceNew.models import ExternalAuthentication
from service.helper.common_connector import CommonConnector
from service.serializer.ogc.tasks import DefaultBehaviourTask
from eulxml import xmlmap
from resourceNew.parsers.capabilities import Service as XmlService


@shared_task(name="async_create_from_parsed_service", base=DefaultBehaviourTask)
def async_create_from_parsed_service(form: dict,
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

        parsed_service = xmlmap.load_xmlobject_from_string(string=connector.content,
                                                           xmlclass=XmlService)
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
