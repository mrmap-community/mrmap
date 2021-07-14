from service.helper.enums import OGCServiceVersionEnum, OGCServiceEnum
from service.serializer.ogc.csw import OGCCatalogueService
from service.serializer.ogc.wfs import OGCWebFeatureService_1_0_0, OGCWebFeatureService_1_1_0, OGCWebFeatureService_2_0_0, \
    OGCWebFeatureService_2_0_2
from service.serializer.ogc.parser.wms import OGCWebMapService_1_0_0, OGCWebMapService_1_1_0, OGCWebMapService_1_1_1, \
    OGCWebMapService_1_3_0
from service.models import ExternalAuthentication


class OGCServiceFactory:
    """Create the correct OGCService objects"""
    @staticmethod
    def get_service_instance(service_type,
                             version: OGCServiceVersionEnum,
                             service_connect_url=None,
                             external_auth: ExternalAuthentication = None):
        service = None
        if service_type is OGCServiceEnum.WMS:
            # create WMS object
            wms_factory = OGCWebMapServiceFactory()
            service = wms_factory.get_service_instance(version=version, service_connect_url=service_connect_url,
                                                       external_auth=external_auth)
        elif service_type is OGCServiceEnum.WFS:
            # create WFS object
            wfs_factory = OGCWebFeatureServiceFactory()
            service = wfs_factory.get_service_instance(version=version, service_connect_url=service_connect_url,
                                                       external_auth=external_auth)
        elif service_type is OGCServiceEnum.CSW:
            # create CSW object
            # We need no factory pattern in here since we do not support different CSW versions
            service = OGCCatalogueService(service_connect_url=service_connect_url, service_version=version,
                                          external_auth=external_auth, service_type=service_type)
        return service


class OGCWebMapServiceFactory:
    """Create the correct OGCWebMapService objects"""

    @staticmethod
    def get_service_instance(version: OGCServiceVersionEnum, service_connect_url=None, external_auth: ExternalAuthentication = None):
        """ Returns the correct implementation of an OGCWebMapService according to the given version

        Args:
            version: The version number of the service
            service_connect_url: The capabilities request uri
        Returns:
            An OGCWebMapService
        """
        if version is OGCServiceVersionEnum.V_1_0_0:
            return OGCWebMapService_1_0_0(service_connect_url=service_connect_url, external_auth=external_auth)
        if version is OGCServiceVersionEnum.V_1_1_0:
            return OGCWebMapService_1_1_0(service_connect_url=service_connect_url, external_auth=external_auth)
        if version is OGCServiceVersionEnum.V_1_1_1:
            return OGCWebMapService_1_1_1(service_connect_url=service_connect_url, external_auth=external_auth)
        if version is OGCServiceVersionEnum.V_1_3_0:
            return OGCWebMapService_1_3_0(service_connect_url=service_connect_url, external_auth=external_auth)


class OGCWebFeatureServiceFactory:
    """Creates the correct OGCWebFeatureService objects"""
    @staticmethod
    def get_service_instance(version: OGCServiceVersionEnum, service_connect_url=None, external_auth: ExternalAuthentication = None):
        """ Returns the correct implementation of an OGCWebFeatureService according to the given version

        Args:
            version: The version number of the service
            service_connect_url: The capabilities request uri
        Returns:
            An OGCWebFeatureService
        """
        if version is OGCServiceVersionEnum.V_1_0_0:
            return OGCWebFeatureService_1_0_0(service_connect_url=service_connect_url, external_auth=external_auth)
        if version is OGCServiceVersionEnum.V_1_1_0:
            return OGCWebFeatureService_1_1_0(service_connect_url=service_connect_url, external_auth=external_auth)
        if version is OGCServiceVersionEnum.V_2_0_0:
            return OGCWebFeatureService_2_0_0(service_connect_url=service_connect_url, external_auth=external_auth)
        if version is OGCServiceVersionEnum.V_2_0_2:
            return OGCWebFeatureService_2_0_2(service_connect_url=service_connect_url, external_auth=external_auth)