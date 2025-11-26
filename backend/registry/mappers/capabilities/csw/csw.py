from odin.mapping import MappingMeta
from registry.mappers.capabilities.base import OgcServiceToXmlMappingBase


class CatalogueServiceToXmlMappingBase(OgcServiceToXmlMappingBase, metaclass=MappingMeta):
    pass
