def get_mapping_class(service):
    from registry.models.service import WebMapService

    if isinstance(service, WebMapService):
        if service.version == "1.3.0":
            from registry.mapping.capabilities.wms.wms130 import \
                WebMapServiceToXml
            return WebMapServiceToXml
