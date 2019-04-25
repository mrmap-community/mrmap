#common classes for handling of WFS (OGC WebFeatureServices)
#http://www.opengeospatial.org/standards/wf
from service.helper.enums import VersionTypes
from service.helper.ogc.wms import OGCWebService
from service.helper import service_helper


class OGCWebFeatureService(OGCWebService):
    class Meta:
        abstract = True

    def create_from_capabilities(self):
        """ Fills the object with data from the capabilities document

        Returns:
             nothing
        """
        # get xml as iterable object
        xml_obj = service_helper.parse_xml(xml=self.service_capabilities_xml)
        if self.service_version is VersionTypes.V_1_0_0:
            self.get_service_metadata_v100(xml_obj=xml_obj)
        if self.service_version is VersionTypes.V_1_1_0:
            self.get_service_metadata_v110(xml_obj=xml_obj)
        if self.service_version is VersionTypes.V_2_0_0:
            #self.get_service_metadata_v200(xml_obj=xml_obj)
            pass
        if self.service_version is VersionTypes.V_2_0_2:
            #self.get_service_metadata_v202(xml_obj=xml_obj)
            pass

class OGCWebFeatureServiceFactory:
    """ Creates the correct OGCWebFeatureService objects

    """
    def get_ogc_wfs(self, version: VersionTypes, service_connect_url: str):
        """ Returns the correct implementation of an OGCWebFeatureService according to the given version

        Args:
            version: The version number of the service
            service_connect_url: The capabilities request uri
        Returns:
            An OGCWebFeatureService
        """
        if version is VersionTypes.V_1_0_0:
            return OGCWebFeatureService_1_0_0(service_connect_url=service_connect_url)
        if version is VersionTypes.V_1_1_0:
            return OGCWebFeatureService_1_1_0(service_connect_url=service_connect_url)
        if version is VersionTypes.V_2_0_0:
            return OGCWebFeatureService_2_0_0(service_connect_url=service_connect_url)
        if version is VersionTypes.V_2_0_2:
            return OGCWebFeatureService_2_0_2(service_connect_url=service_connect_url)


class OGCWebFeatureService_1_0_0(OGCWebFeatureService):
    pass


class OGCWebFeatureService_1_1_0(OGCWebFeatureService):
    pass


class OGCWebFeatureService_2_0_0(OGCWebFeatureService):
    pass


class OGCWebFeatureService_2_0_2(OGCWebFeatureService):
    pass