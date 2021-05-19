from abc import ABC
from celery import Task
from crum import set_current_user, get_current_user
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist

from service.helper.common_connector import CommonConnector
from service.helper.enums import ConnectionEnum
from service.serializer.ogc.factory.factorys import OGCServiceFactory
from service.serializer.ogc.parser.ows import OGCWebServiceParser as OGCWebService
from structure.models import PendingTask, Organization
from celery import shared_task, current_task, group, chain


class PickleSerializer(Task, ABC):
    serializer = 'pickle'


class DefaultBehaviourTask(Task, ABC):

    def __call__(self, owned_by_org_pk, *args, **kwargs):
        if 'created_by_user_pk' in kwargs:
            try:
                user = get_user_model().objects.get(id=kwargs['created_by_user_pk'])
                set_current_user(user)
            except ObjectDoesNotExist:
                return

        try:
            PendingTask.objects.create(task_id=self.request.id,
                                       task_name=self.name,
                                       created_by_user=get_current_user(),
                                       owned_by_org_id=owned_by_org_pk,
                                       meta={
                                           "phase": "Pending..."
                                       })
        except Exception as e:
            import traceback
            traceback.print_exc()

        super().__call__(owned_by_org_pk, *args, **kwargs)


def register_service(service_type, version, base_uri, external_auth, register_for_organization: Organization):
    result = chain(deserialize_from_capabilities.s(service_type, version, base_uri, external_auth) | schedule_get_linked_iso_metadata.s() | to_db.s(register_for_organization, None))()


@shared_task(name="deserialize_from_capabilities")
def deserialize_from_capabilities(service_type, version, base_uri, external_auth):
    factory = OGCServiceFactory()
    service = factory.get_service_instance(service_type=service_type,
                                           version=version,
                                           service_connect_url=base_uri,
                                           external_auth=external_auth)
    service.get_capabilities()
    service.parse_from_capabilities()
    iso_md_list = []
    [iso_md_list.extend(item.iso_metadata) for item in service.root_layer]
    return service, iso_md_list, update_iso_metadata_objects


@shared_task(name="resolve_linked_iso_md")
def get_linked_iso_metadata(uri):
    return OGCWebService.get_linked_iso_metadata(uri)


@shared_task(name="schedule_get_linked_iso_metadata")
def schedule_get_linked_iso_metadata(service, iso_metadata_list, link):
    return group(get_linked_iso_metadata.s(iso_metadata.uri) for iso_metadata in iso_metadata_list | link.s(service))()


@shared_task(name="update_iso_metadata_objects")
def update_iso_metadata_objects(service, results):
    iso_md_list = []
    [iso_md_list.extend(item.iso_metadata) for item in service.root_layer]
    for iso_md in iso_md_list:
        result = next(item for item in results if item["uri"] == iso_md.uri)
        iso_md.raw_metadata = result.get('response', '')
    return service


@shared_task(name="update_iso_metadata_objects")
def to_db(service, register_for_organization):
    return service.to_db(register_for_organization)
