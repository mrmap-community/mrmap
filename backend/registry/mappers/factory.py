from lxml import etree
from registry.mappers.configs import XPATH_MAP
from registry.mappers.xml_mapper import XmlMapper
from registry.mappers.utils import load_file


class OGCServiceXmlMapper(XmlMapper):

    @classmethod
    def from_xml(cls, xml):
        # Root-Element extrahieren
        content = load_file(xml)
        root = etree.fromstring(content)

        root.find

        # Service-Typ anhand des Root-Tags
        tag = etree.QName(root).localname.lower()
        if any(s in tag for s in ["wms", "wmt"]):
            service_type = "WMS"
        elif "wfs" in tag:
            service_type = "WFS"
        elif "capabilities" in tag and "csw" in root.nsmap.keys():
            service_type = "CSW"
        else:
            raise ValueError("Unknown Service-Typ")

        # Version aus Attribut
        version = root.attrib.get("version")
        if not version:
            raise ValueError(
                f"Version could not be detected for {service_type}")

        # Mapping aus Registry auswählen
        mapping = cls._select_mapping(service_type, version)

        return cls(xml=root, mapping=mapping)

    @staticmethod
    def _select_mapping(service_type, version):
        if (service_type, version) in XPATH_MAP:
            return XPATH_MAP[(service_type, version)]
        # Fallback: höchste verfügbare Version
        available_versions = [
            v for (s, v) in XPATH_MAP.keys() if s == service_type]
        if not available_versions:
            raise ValueError(f"No mapping for {service_type}")
        fallback_version = sorted(available_versions, key=lambda v: tuple(
            int(x) for x in v.split(".")))[-1]
        return XPATH_MAP[(service_type, fallback_version)]


class MDMetadataXmlMapper(XmlMapper):

    @classmethod
    def from_xml(cls, xml):
        content = load_file(xml)
        root = etree.fromstring(content)

        md_nodes = root.xpath("//*[local-name()='MD_Metadata']")
        if not md_nodes:
            raise ValueError("No MD_Metadata elements found")

        mappers = []

        for md in md_nodes:
            # ✅ MD_Metadata als eigenes XML-Dokument neu erzeugen
            md_xml = etree.tostring(md, encoding="utf-8")
            md_root = etree.fromstring(md_xml)

            hierarchy = cls._detect_hierarchy_level(md_root)
            mapping = cls._select_mapping(hierarchy)

            mapper = XmlMapper(xml=md_root, mapping=mapping)
            mappers.append(mapper)

        return mappers

    @staticmethod
    def _detect_hierarchy_level(md_node):
        result = md_node.xpath(
            ".//*[local-name()='hierarchyLevel']/*[local-name()='MD_ScopeCode']"
        )

        if not result:
            raise ValueError("Missing hierarchyLevel in MD_Metadata")

        scope = result[0]

        # bevorzugt: codeListValue
        level = scope.attrib.get("codeListValue")

        # fallback: Text
        if not level:
            level = (scope.text or "").strip()

        if not level:
            raise ValueError("Empty hierarchyLevel value")

        return level.lower()

    @staticmethod
    def _select_mapping(hierarchy_level):
        """
        Auswahl des passenden XPath-Mappings anhand hierarchyLevel
        """
        mapping = XPATH_MAP.get(("ISO", hierarchy_level))
        if not mapping:
            raise ValueError(
                f"No mapping for hierarchyLevel '{hierarchy_level}'")
        return mapping
