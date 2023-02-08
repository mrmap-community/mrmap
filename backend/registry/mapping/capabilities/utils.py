from odin.mapping import assign, forward_mapping_factory


def get_import_path_for_xml_mapper(service):
    from registry.models.service import WebMapService

    if isinstance(service, WebMapService):
        if service.version == "1.1.1":
            return "ows_lib.xml_mapper.capabilities.wms.wms111"
        elif service.version == "1.3.0":
            return "ows_lib.xml_mapper.capabilities.wms.wms130"


def get_mapper_for_service(service):
    from registry.models.service import WebMapService

    if isinstance(service, WebMapService):
        if service.version == "1.3.0":
            from ows_lib.xml_mapper.capabilities.wms.wms130 import \
                WebMapService as XmlWebMapService

            from backend.registry.mapping.capabilities.wms.wms import \
                WebMapServiceToXml
            return forward_mapping_factory(from_obj=WebMapService, to_obj=XmlWebMapService, base_mapping=WebMapServiceToXml, mappings=[assign(to_field="keywords", action=WebMapServiceToXml.keywords, to_list=True)])
