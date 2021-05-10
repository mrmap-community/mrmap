from abc import ABC
from celery import Task, shared_task, group

from service.helper import service_helper
from service.helper.enums import OGCServiceEnum
from service.helper.ogc.csw import OGCCatalogueService
from service.helper.ogc.wfs import OGCWebFeatureServiceFactory
from service.helper.ogc.wms import OGCWebMapServiceFactory
from service.models import ExternalAuthentication
from structure.models import Organization


class PickleSerializer(Task, ABC):
    serializer = 'pickle'


def register_service(register_for_organization: str,
                     url_dict: dict,
                     external_auth: dict,
                     quantity: int = 1,
                     **kwargs):
    register_for_organization = Organization.objects.get(pk=register_for_organization)

    iso_metadata_list = collect_iso_metadata.s()
    iso_metadata_list = group(deserialize_iso_md.s(iso_md) for iso_md in )

    chain = deserialize_service.s(url_dict, external_auth) |\
            collect_iso_metadata.s() |\
            group(deserialize_iso_md.s() )
    chain()  # run chain


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
    iso_metadata_temp = []
    for layer in service.layers:
        iso_metadata_temp.extend(layer.iso_metadata)
    return service, iso_metadata_temp


@shared_task(name="deserialize_iso_md", base=PickleSerializer)
def deserialize_iso_md(service, iso_md):
    iso_md.get_and_parse()
    return iso_md
