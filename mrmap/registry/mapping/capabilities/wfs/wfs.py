from importlib import import_module

from odin.mapping import MappingMeta, assign, forward_mapping_factory
from ows_lib.xml_mapper.utils import get_import_path_for_xml_mapper
from registry.mapping.capabilities.base import (
    OgcServiceElementToXmlMappingBase, OgcServiceToXmlMappingBase)
from registry.models.service import FeatureType


class FeatureTypeToXmlMappingBase(OgcServiceElementToXmlMappingBase, metaclass=MappingMeta):
    pass


class WebFeatureServiceToXmlMappingBase(OgcServiceToXmlMappingBase, metaclass=MappingMeta):

    def update(self, *args, **kwargs):
        updated_service = super().update(*args, **kwargs)
        self._update_feature_types()
        return updated_service

    def _update_feature_types(self):
        mappings = []
        mappings.append(assign(to_field="remote_metadata",
                        action=FeatureTypeToXmlMappingBase.remote_metadata, to_list=True))
        mappings.append(assign(to_field="keywords",
                        action=FeatureTypeToXmlMappingBase.keywords, to_list=True))

        for feature_type in self.source.featuretypes.filter(is_active=True):
            xml_feature_type_mapper_cls = getattr(import_module(get_import_path_for_xml_mapper(
                self._destination_obj.serializeDocument())), "FeatureType")
            mapper_cls = forward_mapping_factory(
                from_obj=FeatureType, to_obj=xml_feature_type_mapper_cls, base_mapping=FeatureTypeToXmlMappingBase, mappings=mappings)
            mapper = mapper_cls(source_obj=feature_type)
            mapper.update(destination_obj=self._destination_obj.get_feature_type_by_identifier(
                identifier=feature_type.identifier))

        for feature_type in self.source.featuretypes.filter(is_active=False):
            xml_feature_type = self._destination_obj.get_feature_type_by_identifier(
                identifier=feature_type.identifier)
            if xml_feature_type:
                self._destination_obj.feature_types.remove(xml_feature_type)
