from copy import deepcopy

from odin.mapping import Mapping, assign_field, map_field
from ows_lib.xml_mapper.capabilities.mixins import OperationUrl
from ows_lib.xml_mapper.capabilities.wms.wms130 import Layer as XmlLayer
from ows_lib.xml_mapper.capabilities.wms.wms130 import \
    LayerMetadata as XmlLayerMetadata
from ows_lib.xml_mapper.capabilities.wms.wms130 import \
    RemoteMetadata as XmlRemoteMetadata
from ows_lib.xml_mapper.capabilities.wms.wms130 import \
    ServiceMetadata as XmlServiceMetadata
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


class LayerMetdataToXml(Mapping):
    from_obj = Layer
    to_obj = XmlLayerMetadata

    @assign_field(to_list=True)
    def keywords(self):
        return [str(keyword) for keyword in self.source.keywords.all()]


class LayerToXml(Mapping):
    from_obj = Layer
    to_obj = XmlLayer

    def __init__(self, destination_obj: XmlLayer, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.destionation_obj = destination_obj

    def update(self, *args, **kwargs):
        return super().update(destination_obj=self.destionation_obj, *args, **kwargs)

    @assign_field
    def metadata(self):
        return LayerMetdataToXml(source_obj=self.source).update(destination_obj=deepcopy(self.destionation_obj.metadata))

    # TODO
    # @assign_field
    # def remote_metadata(self):
    #     pass


class ServiceMetadataToXml(Mapping):
    from_obj = WebMapService
    to_obj = XmlServiceMetadata

    @assign_field(to_list=True)
    def keywords(self):
        return [str(keyword) for keyword in self.source.keywords.all()]


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

    @assign_field
    def service_metadata(self):
        """ Updating the service metadata field by using the concrete mapper and a deep copy of the old xml object

        .. note::
           Can't be handled by the apply function as predicted in https://github.com/python-odin/odin/issues/137#issuecomment-1408750868
           Cause the xml mapper objects only handles a subset of all xpaths which are present in a capabilities document (only database relevant fields), 
           the usage of apply will create a new fresh xml mapper object with just the xml structure of the concrete attributes which are handled by it. 
           So this will not represent the full valid xml structure of a valid capabilities document. So we need to update the existing xml objects. 

        .. note:: 
           Update routine from the odin package will only work if the object instances are not the same, 
           cause otherwise the setattr() will result in empty data. 
           Don't know why... 
           So it is necessary to do a deepcopy of the existing object first.
        """
        return ServiceMetadataToXml(source_obj=self.source).update(
            destination_obj=deepcopy(self.xml.service_metadata))
