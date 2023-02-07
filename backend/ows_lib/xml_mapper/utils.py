from importlib import import_module
from pathlib import Path

from eulxml.xmlmap import (StringField, XmlObject, load_xmlobject_from_file,
                           load_xmlobject_from_string)
from ows_lib.xml_mapper.namespaces import NS_WC
from registry.enums.service import OGCServiceEnum
from registry.xmlmapper.exceptions import SemanticError


def raise_default_sematic_error(kind: str):
    raise SemanticError(f"could not determine the service type for the parsed capabilities document. "
                        f"Parsed name was {kind}")


class OGCServiceTypeHelper(XmlObject):
    """Helper class to extract version and service type from capabilities document.
       Not for Common usage!
    """

    version = StringField(xpath="//@version")
    _kind = StringField(
        xpath=f"./{NS_WC}Service']/{NS_WC}Name']|./{NS_WC}ServiceIdentification']/{NS_WC}ServiceType']")

    @property
    def kind(self):
        if not self._kind:
            raise SemanticError(
                "could not determine the service type for the parsed capabilities document.")
        _kind = self._kind.lower()

        if ":" in _kind:
            _kind = _kind.split(":", 1)[-1]
        elif " " in _kind:
            _kind = _kind.split(" ", 1)[-1]

        if _kind not in ["wms", "wfs", "csw"]:
            raise_default_sematic_error(_kind)
        return _kind


def get_load_func(capabilities_xml):
    if isinstance(capabilities_xml, str) or isinstance(capabilities_xml, bytes):
        load_func = load_xmlobject_from_string
    elif isinstance(capabilities_xml, Path):
        capabilities_xml = capabilities_xml.resolve().__str__()
        load_func = load_xmlobject_from_file
    else:
        raise ValueError("xml must be ether a str or Path")
    return load_func


def get_ogc_service_type_helper(capabilities_xml: OGCServiceTypeHelper):
    load_func = get_load_func(capabilities_xml)
    return load_func(capabilities_xml, xmlclass=OGCServiceTypeHelper)


def get_import_path_for_xml_mapper(capabilities_xml):
    parsed_service: OGCServiceTypeHelper = get_ogc_service_type_helper(
        capabilities_xml=capabilities_xml)

    if parsed_service.kind == OGCServiceEnum.WMS.value:
        match parsed_service.version:
            case "1.1.1":
                return "ows_lib.xml_mapper.capabilities.wms.wms111"
            case "1.3.0":
                return "ows_lib.xml_mapper.capabilities.wms.wms130"
            case _:
                raise NotImplementedError(
                    f"Version {parsed_service.version} for wms is not supported.")
    elif parsed_service.kind == OGCServiceEnum.WFS.value:
        match parsed_service.version:
            case "2.0.0":
                return "ows_lib.xml_mapper.capabilities.wfs.wfs200"
            case _:
                raise NotImplementedError(
                    f"Version {parsed_service.version} for wfs is not supported.")
    elif parsed_service.kind == OGCServiceEnum.CSW.value:
        match parsed_service.version:
            case "2.0.2":
                return "ows_lib.xml_mapper.capabilities.csw.csw202"
        raise NotImplementedError(
            f"Version {parsed_service.version} for csw is not supported.")


def get_xml_mapper(capabilities_xml):
    """helper function to get the correct xml mapper class for a given capabilities xml"""

    import_path = get_import_path_for_xml_mapper(
        capabilities_xml=capabilities_xml)

    parsed_service: OGCServiceTypeHelper = get_ogc_service_type_helper(
        capabilities_xml=capabilities_xml)

    if parsed_service.kind == OGCServiceEnum.WMS.value:
        return getattr(import_module(import_path), "WebMapService")
    elif parsed_service.kind == OGCServiceEnum.WFS.value:
        return getattr(import_module(import_path), "WebFeatureService")
    elif parsed_service.kind == OGCServiceEnum.CSW.value:
        return getattr(import_module(import_path), "CatalogueService")
    else:
        raise_default_sematic_error(parsed_service.kind)


def get_parsed_service(capabilities_xml):
    load_func = get_load_func(capabilities_xml)
    xml_mapper = get_xml_mapper(capabilities_xml)
    return load_func(capabilities_xml, xmlclass=xml_mapper)
