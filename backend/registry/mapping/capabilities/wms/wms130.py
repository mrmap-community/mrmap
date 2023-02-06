import importlib

from odin.mapping import Mapping, assign_field, map_field, mapping_factory
from ows_lib.xml_mapper.utils import get_import_path_for_xml_mapper
from registry.mapping.capabilities.mixins import OgcServiceToXmlMixin
from registry.mapping.capabilities.utils import get_mapper_for_layer
from registry.models.metadata import DatasetMetadata, Style


class MetadataUrlToXml(Mapping):

    @map_field(from_field="origin_url")
    def link(self, value):
        return value


class LayerToXml(Mapping):

    def __init__(self, destination_obj, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.destionation_obj = destination_obj

    def update(self, *args, **kwargs):
        return super().update(destination_obj=self.destionation_obj, *args, **kwargs)

    @assign_field(to_list=True)
    def keywords(self):
        return [str(keyword) for keyword in self.source.keywords.all()]

    @assign_field(to_list=True)
    def styles(self):
        # FIXME: find style and update instead of creating them with apply
        xml_style_mapper_cls = importlib.import_module(
            get_import_path_for_xml_mapper(f"{self.destionation_obj.serializeDocument()}.Style"))
        stye_mapper = mapping_factory(
            from_obj=Style, to_obj=xml_style_mapper_cls)
        _styles = []
        for style in self.source.styles.all():
            _styles.append(stye_mapper.apply(source_obj=style))
        return _styles

    @assign_field(to_list=True)
    def remote_metadata(self):
        # FIXME: find style and update instead of creating them with apply
        xml_metadata_url_mapper_cls = importlib.import_module(get_import_path_for_xml_mapper(
            f"{self.destionation_obj.serializeDocument()}.RemoteMetadata"))
        remote_metadata_mapper = mapping_factory(
            from_obj=DatasetMetadata, to_obj=xml_metadata_url_mapper_cls)
        _remote_metadata = []
        for remote_metadata in self.source.dataset_metadata_relations.all():
            _remote_metadata.append(
                remote_metadata_mapper.apply(source_obj=remote_metadata))
        return _remote_metadata


class WebMapServiceToXml(OgcServiceToXmlMixin, Mapping):

    def update(self, *args, **kwargs):
        updated_service = super().update(*args, **kwargs)
        self._update_layers()
        return updated_service

    def _update_layers(self):
        for layer in self.source.layers.filter(is_active=True):
            xml_layer_mapper_cls = importlib.import_module(get_import_path_for_xml_mapper(
                f"{self.destionation_obj.serializeDocument()}.Layer"))

            LayerToXml(source_obj=layer, destination_obj=self.destination_obj.get_layer_by_identifier(
                identifier=layer.identifier)).update()
        for layer in self.source.layers.filter(is_active=False):
            xml_layer = self.destination_obj.get_layer_by_identifier(
                identifier=layer.identifier)
            if xml_layer:
                del xml_layer
