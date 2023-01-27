from odin.mapping import Mapping, map_field
from ows_lib.xml_mapper.capabilities.wms.wms130 import \
    WebMapService as XmlWebMapService
from registry.models.service import WebMapService


class WebMapServiceToXml(Mapping):
    from_obj = WebMapService
    to_obj = XmlWebMapService

    @map_field(from_field='title', to_field='service_metadata.title')
    def title(self, value):
        return value
