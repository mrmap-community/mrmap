from abc import ABC
from celery import Task, shared_task, group
from crum import set_current_user, get_current_user
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist

from service.helper import service_helper
from service.helper.enums import OGCServiceEnum
from service.helper.ogc.csw import OGCCatalogueService
from service.helper.ogc.wfs import OGCWebFeatureServiceFactory
from service.helper.ogc.wms import OGCWebMapServiceFactory
from service.models import ExternalAuthentication
from structure.models import Organization, PendingTask


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


def register_service(register_for_organization: str,
                     url_dict: dict,
                     external_auth: dict,
                     quantity: int = 1,
                     **kwargs):
    # register_for_organization = Organization.objects.get(pk=register_for_organization)

    service = deserialize_service.s(url_dict, external_auth)
    iso_metadata_list = collect_iso_metadata.s()
    deserialized_md = group(deserialize_iso_md.s(iso_md) for iso_md in iso_metadata_list.get('iso_metadata_list'))

    chain = deserialize_service.s(url_dict, external_auth) | collect_iso_metadata.s()
    chain()  # run chain
    result = chain.get()

    print(result)
    i = 0


@shared_task(name="deserialize_service", base=PickleSerializer)
def deserialize_service(url_dict, external_auth: dict = None):
    service_type = url_dict.get("service")
    version = url_dict.get("version")
    base_uri = url_dict.get("base_uri")

    if external_auth:
        # todo:
        external_auth = ExternalAuthentication(
            username=external_auth["username"],
            password=external_auth["password"],
            auth_type=external_auth["auth_type"],
        )

    service = None
    if service_type is OGCServiceEnum.WMS:
        # create WMS object
        wms_factory = OGCWebMapServiceFactory()
        service = wms_factory.get_ogc_wms(version=version, service_connect_url=base_uri, external_auth=external_auth)

    elif service_type is OGCServiceEnum.WFS:
        # create WFS object
        wfs_factory = OGCWebFeatureServiceFactory()
        service = wfs_factory.get_ogc_wfs(version=version, service_connect_url=base_uri, external_auth=external_auth)

    elif service_type is OGCServiceEnum.CSW:
        # create CSW object
        # We need no factory pattern in here since we do not support different CSW versions
        service = OGCCatalogueService(service_connect_url=base_uri, service_version=version, external_auth=external_auth, service_type=service_type)

    else:
        # For future implementation
        pass

    service.get_capabilities()
    service.deserialize_from_capabilities()

    return service


@shared_task(name="collect_iso_metadata", base=PickleSerializer)
def collect_iso_metadata(service):
    iso_metadata_list = []
    for layer in service.layers:
        iso_metadata_list.extend(layer.iso_metadata)
    return {'service': service,
            'iso_metadata_list': iso_metadata_list}


@shared_task(name="deserialize_iso_md", base=PickleSerializer)
def deserialize_iso_md(service, iso_md):
    iso_md.get_and_parse()
    return iso_md
