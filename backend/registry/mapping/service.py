from copy import deepcopy

from odin.mapping import Mapping, assign_field
from ows_lib.xml_mapper.capabilities.wms.wms130 import Layer as XmlLayer
from ows_lib.xml_mapper.capabilities.wms.wms130 import \
    LayerMetadata as XmlLayerMetadata
from ows_lib.xml_mapper.capabilities.wms.wms130 import \
    ServiceMetadata as XmlServiceMetadata
from ows_lib.xml_mapper.capabilities.wms.wms130 import \
    WebMapService as XmlWebMapService
from registry.models.service import Layer, WebMapService


class LayerMetdataToXml(Mapping):
    from_obj = Layer
    to_obj = XmlLayerMetadata


class LayerToXml(Mapping):
    from_obj = Layer
    to_obj = XmlLayer

    def __init__(self, xml_service: XmlWebMapService, xml_layer: XmlLayer, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.xml_service = xml_service
        self.xml_layer = xml_layer

    @assign_field
    def children(self):
        child_list = []
        for child in self.source.get_children():
            destination_obj = self.xml_service.get_layer_by_identifier(
                identifier=child.identifier)
            child_list.append(LayerToXml(xml_service=self.xml_service, xml_layer=destination_obj, source_obj=child).update(
                destination_obj=deepcopy(destination_obj)))
        return child_list

    @assign_field
    def metadata(self):
        return LayerMetdataToXml(source_obj=self.source).update(destination_obj=deepcopy(self.xml_layer.metadata))


class ServiceMetadataToXml(Mapping):
    from_obj = WebMapService
    to_obj = XmlServiceMetadata


class WebMapServiceToXml(Mapping):
    from_obj = WebMapService
    to_obj = XmlWebMapService

    def __init__(self, xml: XmlWebMapService, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.xml = xml

    @assign_field
    def root_layer(self):
        return LayerToXml(xml_service=self.xml, xml_layer=self.xml.root_layer, source_obj=self.source.root_layer).update(destination_obj=deepcopy(self.xml.root_layer))

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
