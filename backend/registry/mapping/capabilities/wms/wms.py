from importlib import import_module

from odin.mapping import MappingMeta, assign, forward_mapping_factory
from ows_lib.xml_mapper.utils import get_import_path_for_xml_mapper
from registry.mapping.capabilities.base import (
    OgcServiceElementToXmlMappingBase, OgcServiceToXmlMappingBase)
from registry.models.metadata import Style
from registry.models.service import Layer


class LayerToXmlMappingBase(OgcServiceElementToXmlMappingBase, metaclass=MappingMeta):

    def styles(self):
        # FIXME: find style and update instead of creating them with apply
        xml_style_mapper_cls = getattr(import_module(
            get_import_path_for_xml_mapper(self._destination_obj.serializeDocument())), "Style")
        style_mapper_cls = forward_mapping_factory(
            from_obj=Style, to_obj=xml_style_mapper_cls)
        _styles = []
        for style in self.source.styles.all():
            _styles.append(style_mapper_cls.apply(source_obj=style))
        return _styles


class WebMapServiceToXmlMappingBase(OgcServiceToXmlMappingBase, metaclass=MappingMeta):

    def update(self, *args, **kwargs):
        updated_service = super().update(*args, **kwargs)
        self._update_layers()
        return updated_service

    def _update_layers(self):
        mappings = []
        mappings.append(assign(to_field="remote_metadata",
                        action=LayerToXmlMappingBase.remote_metadata, to_list=True))
        mappings.append(
            assign(to_field="styles", action=LayerToXmlMappingBase.styles, to_list=True))
        mappings.append(assign(to_field="keywords",
                        action=LayerToXmlMappingBase.keywords, to_list=True))

        for layer in self.source.layers.filter(is_active=True):
            xml_layer_mapper_cls = getattr(import_module(get_import_path_for_xml_mapper(
                self._destination_obj.serializeDocument())), "Layer")
            layer_mapper_cls = forward_mapping_factory(
                from_obj=Layer, to_obj=xml_layer_mapper_cls, base_mapping=LayerToXmlMappingBase, mappings=mappings)
            layer_mapper = layer_mapper_cls(source_obj=layer)
            layer_mapper.update(destination_obj=self._destination_obj.get_layer_by_identifier(
                identifier=layer.identifier))

        for layer in self.source.layers.filter(is_active=False):
            xml_layer = self._destination_obj.get_layer_by_identifier(
                identifier=layer.identifier)
            if xml_layer:
                self._destination_obj._layers.remove(xml_layer)
