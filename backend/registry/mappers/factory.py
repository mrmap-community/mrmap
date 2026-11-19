from lxml import etree

from registry import models
from registry.exceptions.metadata import UnknownMetadataKind
from registry.mappers.cache import LocalXmlCache
from registry.mappers.configs import XPATH_MAP
from registry.mappers.utils import load_file
from registry.mappers.xml_mapper import XmlMapper


class OGCServiceXmlMapper(XmlMapper):

    @classmethod
    def from_xml(cls, xml):
        # Root-Element extrahieren
        content = load_file(xml)
        root = etree.fromstring(content)

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

    @classmethod
    def to_xml(cls, instance: "models.DocumentModelMixin") -> etree.ElementTree:
        mapper = cls.from_xml(instance.xml_backup_file)
        return mapper.django_to_xml(instance)

    @staticmethod
    def _select_mapping(service_type, version):
        if (service_type, version) in XPATH_MAP:
            return XPATH_MAP[(service_type, version)]
        # Fallback: höchste verfügbare Version
        available_versions = [
            v for (s, v) in XPATH_MAP.keys() if s == service_type]
        if not available_versions:
            raise ValueError(f"No mapping for {service_type}")
        fallback_version = max(available_versions, key=lambda v: tuple(
            int(x) for x in v.split(".")))
        return XPATH_MAP[(service_type, fallback_version)]


class MDMetadataXmlMapper(XmlMapper):
    # The record type a document names for itself in its hierarchyLevel,
    # answered on the detection path of from_xml and read by the bucket check
    # of a harvesting import instead of asking the tree a second time (#1415).
    # None for a mapper built with a forced kind or outside from_xml.
    hierarchy_level = None

    @classmethod
    def from_xml(cls, xml, cache=None, hierarchy_level=None):
        """Build one mapper per MD_Metadata node of the document.

        Args:
            xml: the XML source, see XmlMapper.
            cache: cache for the parsed instances; None keeps the default
                GlobalXmlCache of the harvesting path, a LocalXmlCache runs
                the mapping without touching process-global state (#981).
            hierarchy_level: interpret every node with the mapping of this
                record type instead of detecting hierarchyLevel; an unknown
                type raises just like the detection path does (#981).
        """
        content = load_file(xml)
        root = etree.fromstring(content)

        md_nodes = root.xpath("//*[local-name()='MD_Metadata']")
        if not md_nodes:
            raise ValueError("No MD_Metadata elements found")

        mappers = []

        for md in md_nodes:
            if len(md_nodes) == 1 and md.getparent() is None:
                # the node is the whole document: the copy below would
                # serialize and reparse it for a structurally identical tree.
                # Every file a harvesting stores per record and every
                # advertised document a registration downloads has this shape,
                # so the import of one document pays one parse, not three
                # transformations (#1415). The traversal of a mapper only ever
                # reads its tree; the writers which change a document build
                # their mapper from the bytes they own.
                md_root = md
            else:
                # ✅ MD_Metadata als eigenes XML-Dokument neu erzeugen: a node
                # below a search-response wrapper, or one of several, only
                # answers the deterministic paths of a standalone document -
                # and the backup of one record only carries its own record -
                # after the serialize-and-reparse copy.
                md_root = etree.fromstring(
                    etree.tostring(md, encoding="utf-8"))

            if hierarchy_level is None:
                detected = cls._detect_hierarchy_level(md_root)
                hierarchy = detected
            else:
                # a forced kind is the caller's interpretation of the node and
                # never travels as the document's own answer
                detected = None
                hierarchy = hierarchy_level
            mapping = cls._select_mapping(hierarchy)

            mapper = cls(xml=md_root, mapping=mapping, cache=cache)
            if detected is not None:
                # what the document named for itself, which the bucket check
                # of a harvesting import reads here instead of running the
                # same traversal over the hierarchyLevel element again (#1415)
                mapper.hierarchy_level = detected
            mappers.append(mapper)

        return mappers

    @classmethod
    def extract_mapped_values(cls, xml, hierarchy_level=None):
        """Map an ISO 19139 document to plain values, without persistence.

        The one entry point of #981 for callers which need what a document
        says but must not write anything: no PersistenceHandler, no database
        write, no network request, no process-global cache entry. Every
        MD_Metadata node of the document is mapped with its config - found via
        hierarchyLevel or forced through hierarchy_level - by exactly the
        traversal the harvesting path runs, and the answer describes one
        record per node:

            {"spec": "dataset",                       # the mapping config key
             "model": "registry.DatasetMetadataRecord",
             "values": {**mapped fields of the record**}}

        The values dict carries every mapped field: scalars as parsed, parsed
        relations as nested dicts and lists, and the epic #669 access and
        coupling elements (online_links, distributor_online_links, operations,
        operates_on, coupled_resources) as ordered lists of plain dicts with
        their original external values.
        """
        records = []
        for mapper in cls.from_xml(
                xml, cache=LocalXmlCache(), hierarchy_level=hierarchy_level):
            mapper.xml_to_django()
            for spec_key, mapped in mapper.mapped_values().items():
                model_label = mapper.mapping[spec_key].get("_model")
                for values in mapped:
                    records.append({
                        "spec": spec_key,
                        "model": model_label,
                        "values": values,
                    })
        return records

    @classmethod
    def write_mapped_records(cls, xml, records, hierarchy_level=None):
        """Write mapped records back into an ISO 19139 document (#1242).

        The inverse of extract_mapped_values(): takes the document and one
        record per MD_Metadata node - in document order, in the shape the
        extraction answers ({"spec", "model", "values"} or a bare values
        dict) - and returns the serialized document with those values
        written in. The same traversal machinery, configs and parsers serve
        both directions, so what the editor shows is exactly what it can
        write.

        Unmapped content is carried through untouched; a write never
        removes more than surplus rows of a collection it was asked to
        rewrite, and fields without a reverse mapping are skipped and named
        in the answer. Node identity is preserved: the MD_Metadata nodes are
        written inside the live tree - unlike from_xml(), which detaches
        each node into its own document and would drop every write.

        Args:
            xml: the XML source, see load_file.
            records: one dict per MD_Metadata node of the document.
            hierarchy_level: force the record kind like extract_mapped_values.

        Returns:
            (bytes, list) of the serialized document and the warnings the
            mappers collected while writing.

        Raises:
            ValueError: when the record count does not match the node count
                or a record does not belong to the record kind its node maps
                as.
        """
        content = load_file(xml)
        root = etree.fromstring(content)

        md_nodes = root.xpath("//*[local-name()='MD_Metadata']")
        if not md_nodes:
            raise ValueError("No MD_Metadata elements found")
        if len(md_nodes) != len(records):
            raise ValueError(
                f"the document carries {len(md_nodes)} MD_Metadata nodes, "
                f"{len(records)} records were given")

        warnings = []
        for md_node, record in zip(md_nodes, records):
            hierarchy = hierarchy_level or cls._detect_hierarchy_level(md_node)
            mapping = cls._select_mapping(hierarchy)
            spec_key = next(
                (key for key, value in mapping.items()
                 if not key.startswith("_") and isinstance(value, dict)
                 and "_model" in value), None)
            model_label = mapping[spec_key].get("_model")
            given_spec = record.get("spec")
            given_model = record.get("model")
            if given_spec not in (None, spec_key) or \
                    given_model not in (None, model_label):
                raise ValueError(
                    f"record for '{given_spec or given_model}' does not map "
                    f"to the document's kind '{spec_key}'")
            values = record.get("values", record)
            mapper = cls(xml=md_node, mapping=mapping, cache=LocalXmlCache())
            mapper.write_mapped_values(values)
            warnings.extend(mapper.warnings)

        return etree.tostring(
            root, xml_declaration=True, encoding="utf-8"), warnings

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
            # The kind the document names for itself is not a kind Mr. Map
            # maps. Named as its own error, so a caller can tell an unmapped
            # document apart from a document it could not read (#1260); as a
            # ValueError every caller which already reads it as a bad value
            # keeps its answer.
            raise UnknownMetadataKind(
                f"No mapping for hierarchyLevel '{hierarchy_level}'")
        return mapping
