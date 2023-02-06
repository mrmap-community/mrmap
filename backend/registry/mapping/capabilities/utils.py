from odin.mapping import mapping_factory


def get_import_path_for_xml_mapper(service):
    from registry.models.service import WebMapService

    if isinstance(service, WebMapService):
        if service.version == "1.1.1":
            return "ows_lib.xml_mapper.capabilities.wms.wms111"
        elif service.version == "1.3.0":
            return "ows_lib.xml_mapper.capabilities.wms.wms130"


def get_mapper_for_layer(service):
    from registry.models.service import Layer, WebMapService

    if isinstance(service, WebMapService):
        if service.version == "1.3.0":
            from ows_lib.xml_mapper.capabilities.wms.wms130 import \
                Layer as XmlLayer
            from registry.mapping.capabilities.wms.wms130 import LayerToXml
            return mapping_factory(from_obj=Layer, to_obj=XmlLayer, base_mapping=LayerToXml, generate_reverse=False)


def get_mapper_for_service(service):
    from registry.models.service import WebMapService

    if isinstance(service, WebMapService):
        if service.version == "1.3.0":
            from ows_lib.xml_mapper.capabilities.wms.wms130 import \
                WebMapService as XmlWebMapService
            from registry.mapping.capabilities.wms.wms130 import \
                WebMapServiceToXml
            return mapping_factory(from_obj=WebMapService, to_obj=XmlWebMapService, base_mapping=WebMapServiceToXml, generate_reverse=False)


def get_mapping_class(service):
    from registry.models.service import WebMapService

    if isinstance(service, WebMapService):
        if service.version == "1.3.0":
            from registry.mapping.capabilities.wms.wms130 import \
                WebMapServiceToXml
            return WebMapServiceToXml
