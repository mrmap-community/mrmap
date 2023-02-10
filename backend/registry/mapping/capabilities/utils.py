from odin.mapping import assign, forward_mapping_factory


def get_import_path_for_xml_mapper(service):
    from registry.models.service import WebMapService

    if isinstance(service, WebMapService):
        if service.version == "1.1.1":
            return "ows_lib.xml_mapper.capabilities.wms.wms111"
        elif service.version == "1.3.0":
            return "ows_lib.xml_mapper.capabilities.wms.wms130"


def get_mapper_for_service(service):
    from registry.models.service import WebFeatureService, WebMapService

    if isinstance(service, WebMapService):
        from registry.mapping.capabilities.wms.wms import WebMapServiceToXml
        if service.version == "1.1.1":
            from ows_lib.xml_mapper.capabilities.wms.wms111 import \
                WebMapService as XmlWebMapService
        elif service.version == "1.3.0":
            from ows_lib.xml_mapper.capabilities.wms.wms130 import \
                WebMapService as XmlWebMapService
        else:
            raise NotImplementedError(
                f"wms of version: {service.version} is not supported.")
        return forward_mapping_factory(from_obj=WebMapService, to_obj=XmlWebMapService, base_mapping=WebMapServiceToXml, mappings=[assign(to_field="keywords", action=WebMapServiceToXml.keywords, to_list=True)])
    elif isinstance(service, WebFeatureService):
        from registry.mapping.capabilities.wfs.wfs import \
            WebFeatureServiceToXml

        if service.version == "2.0.0":
            from ows_lib.xml_mapper.capabilities.wfs.wfs200 import \
                WebFeatureService as XmlWebFeatureService
        else:
            raise NotImplementedError(
                f"wfs of version: {service.version} is not supported.")
        return forward_mapping_factory(from_obj=WebFeatureService, to_obj=XmlWebFeatureService, base_mapping=WebFeatureServiceToXml, mappings=[assign(to_field="keywords", action=WebFeatureServiceToXml.keywords, to_list=True)])
