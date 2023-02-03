from copy import deepcopy

from odin.mapping import Mapping, assign_field, map_field
from ows_lib.xml_mapper.capabilities.mixins import OperationUrl
from ows_lib.xml_mapper.capabilities.wms.wms130 import Layer as XmlLayer
from ows_lib.xml_mapper.capabilities.wms.wms130 import \
    RemoteMetadata as XmlRemoteMetadata
from ows_lib.xml_mapper.capabilities.wms.wms130 import \
    WebMapService as XmlWebMapService
from registry.models.metadata import DatasetMetadata
from registry.models.service import Layer, WebMapService


class MetadataUrlToXml(Mapping):
    from_obj = DatasetMetadata
    to_obj = XmlRemoteMetadata

    @map_field(from_field="origin_url")
    def link(self, value):
        return value


class LayerToXml(Mapping):
    from_obj = Layer
    to_obj = XmlLayer

    def __init__(self, destination_obj: XmlLayer, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.destionation_obj = destination_obj

    def update(self, *args, **kwargs):
        return super().update(destination_obj=self.destionation_obj, *args, **kwargs)

    @assign_field(to_list=True)
    def keywords(self):
        return [str(keyword) for keyword in self.source.keywords.all()]

    # TODO
    # @assign_field
    # def remote_metadata(self):
    #     pass


class WebMapServiceToXml(Mapping):
    from_obj = WebMapService
    to_obj = XmlWebMapService

    def __init__(self, destination_obj: XmlWebMapService, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.xml = deepcopy(destination_obj)

    def update(self, *args, **kwargs):
        updated_service = super().update(destination_obj=self.xml, *args, **kwargs)
        self._update_layers()
        self._update_operation_urls(updated_service=updated_service)
        return updated_service

    def _update_layers(self):
        for layer in self.source.layers.filter(is_active=True):
            LayerToXml(source_obj=layer, destination_obj=self.xml.get_layer_by_identifier(
                identifier=layer.identifier)).update()
        for layer in self.source.layers.filter(is_active=False):
            xml_layer = self.xml.get_layer_by_identifier(
                identifier=layer.identifier)
            if xml_layer:
                del xml_layer

    def _update_operation_urls(self, updated_service):
        operation_urls = []
        for operation_url in self.source.operation_urls.all():
            operation_urls.append(
                OperationUrl(
                    method=operation_url.method,
                    url=operation_url.url,
                    operation=operation_url.operation,
                    mime_types=[str(mime_type) for mime_type in operation_url.mime_types.all()]))
        updated_service.operation_urls = operation_urls

    @assign_field(to_list=True)
    def keywords(self):
        return [str(keyword) for keyword in self.source.keywords.all()]
