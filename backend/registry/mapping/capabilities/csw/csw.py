from copy import deepcopy

from odin.mapping import MappingBase, MappingMeta
from ows_lib.xml_mapper.capabilities.mixins import OperationUrl


class CatalogueServiceToXml(MappingBase, metaclass=MappingMeta):

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
