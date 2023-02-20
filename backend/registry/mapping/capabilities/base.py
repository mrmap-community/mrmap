from copy import deepcopy
from importlib import import_module

from odin.mapping import MappingBase, define, forward_mapping_factory
from ows_lib.xml_mapper.capabilities.mixins import OperationUrl
from ows_lib.xml_mapper.utils import get_import_path_for_xml_mapper
from registry.models.metadata import DatasetMetadata


class OgcServiceElementToXmlMappingBase(MappingBase):

    def update(self, destination_obj, *args, **kwargs):
        self._destination_obj = destination_obj
        return super().update(destination_obj=self._destination_obj, *args, **kwargs)

    def keywords(self):
        return [str(keyword) for keyword in self.source.keywords.all()]

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


class OgcServiceToXmlMappingBase(MappingBase):

    def keywords(self):
        return [str(keyword) for keyword in self.source.keywords.all()]

    def update(self, destination_obj, *args, **kwargs):
        self._destination_obj = deepcopy(destination_obj)
        updated_service = super().update(
            destination_obj=self._destination_obj, *args, **kwargs)
        self._update_operation_urls(updated_service=updated_service)
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
