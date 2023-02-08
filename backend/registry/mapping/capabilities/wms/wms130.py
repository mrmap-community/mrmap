from copy import deepcopy
from importlib import import_module

from odin.mapping import (MappingBase, MappingMeta, assign, define,
                          forward_mapping_factory)
from ows_lib.xml_mapper.capabilities.mixins import OperationUrl
from ows_lib.xml_mapper.utils import get_import_path_for_xml_mapper
from registry.models.metadata import DatasetMetadata, Style
from registry.models.service import Layer


class LayerToXml(MappingBase, metaclass=MappingMeta):

    def update(self, destination_obj, *args, **kwargs):
        self._destination_obj = destination_obj
        return super().update(destination_obj=self._destination_obj, *args, **kwargs)

    def keywords(self):
        return [str(keyword) for keyword in self.source.keywords.all()]

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

    def remote_metadata(self):
        # FIXME: find style and update instead of creating them with apply
        xml_metadata_url_mapper_cls = getattr(
            import_module(
                get_import_path_for_xml_mapper(
                    self._destination_obj.serializeDocument()
                )
            ),
            "RemoteMetadata")
        remote_metadata_mapper_cls = forward_mapping_factory(
            from_obj=DatasetMetadata, to_obj=xml_metadata_url_mapper_cls, mappings=[define(from_field="origin_url", to_field="link")])
        _remote_metadata = []
        for remote_metadata in self.source.dataset_metadata_relations.all():
            _remote_metadata.append(
                remote_metadata_mapper_cls.apply(source_obj=remote_metadata))
        return _remote_metadata


class WebMapServiceToXml(MappingBase, metaclass=MappingMeta):

    def keywords(self):
        return [str(keyword) for keyword in self.source.keywords.all()]

    def update(self, destination_obj, *args, **kwargs):
        self._destination_obj = deepcopy(destination_obj)
        updated_service = super().update(
            destination_obj=self._destination_obj, *args, **kwargs)
        self._update_operation_urls(updated_service=updated_service)
        self._update_layers()
        return updated_service

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

    def _update_layers(self):
        mappings = []
        mappings.append(assign(to_field="remote_metadata",
                        action=LayerToXml.remote_metadata, to_list=True))
        mappings.append(
            assign(to_field="styles", action=LayerToXml.styles, to_list=True))
        mappings.append(assign(to_field="keywords",
                        action=LayerToXml.keywords, to_list=True))

        for layer in self.source.layers.filter(is_active=True):
            xml_layer_mapper_cls = getattr(import_module(get_import_path_for_xml_mapper(
                self._destination_obj.serializeDocument())), "Layer")
            layer_mapper_cls = forward_mapping_factory(
                from_obj=Layer, to_obj=xml_layer_mapper_cls, base_mapping=LayerToXml, mappings=mappings)
            layer_mapper = layer_mapper_cls(source_obj=layer)
            layer_mapper.update(destination_obj=self._destination_obj.get_layer_by_identifier(
                identifier=layer.identifier))

        for layer in self.source.layers.filter(is_active=False):
            xml_layer = self._destination_obj.get_layer_by_identifier(
                identifier=layer.identifier)
            if xml_layer:
                del xml_layer
