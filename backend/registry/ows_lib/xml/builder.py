from importlib import resources

from lxml import etree
from registry.ows_lib.xml.consts import XSD_LOOKUP

XS_NS = "http://www.w3.org/2001/XMLSchema"
XS = f"{{{XS_NS}}}"


class XSDSkeletonBuilder:
    def __init__(self, schema_key: tuple[str, str, str]):
        """
        schema_key: (service, schema_name, version)
        Example: ('csw', 'discovery', '2.0.2')
        """
        self._loaded_schemas = set()
        self.elements = {}           # (tns, name) -> element
        self.types = {}              # (tns, name) -> complexType
        self.attribute_groups = {}   # (tns, name) -> attributeGroup
        self.parents = {}            # child_name -> list of parent type names

        # Lookup XSD filename
        try:
            xsd_filename = XSD_LOOKUP[schema_key]
        except KeyError:
            raise ValueError(f"Unsupported schema lookup: {schema_key}")

        schema_dir = resources.files("registry.ows_lib.xml.schemas")
        with schema_dir.joinpath(xsd_filename).open("rb") as f:
            xsd_bytes = f.read()

        self.root = etree.fromstring(xsd_bytes)

        # Register as loaded
        self._loaded_schemas.add(self._schema_id(self.root, xsd_filename))

        # Resolve imports/includes recursively
        self._resolve_external_schemas(self.root)

        # Index elements/types
        self._index_schema(self.root)

    # ------------------------- Schema utilities -------------------------
    def _schema_id(self, root, source=None):
        return (root.get("targetNamespace"), source)

    def _resolve_external_schemas(self, root):
        schema_dir = resources.files("registry.ows_lib.xml.schemas")
        for tag in ("include", "import"):
            for node in root.findall(f"{XS}{tag}"):
                schema_location = node.get("schemaLocation")
                if not schema_location:
                    continue
                try:
                    with schema_dir.joinpath(schema_location).open("rb") as f:
                        xsd_bytes = f.read()
                except FileNotFoundError:
                    continue  # skip missing schemas

                external_root = etree.fromstring(xsd_bytes)
                schema_id = self._schema_id(external_root, schema_location)
                if schema_id in self._loaded_schemas:
                    continue

                self._loaded_schemas.add(schema_id)
                self._resolve_external_schemas(external_root)
                self._index_schema(external_root)

    # ------------------------- Indexing -------------------------
    def _index_schema(self, root):
        tns = root.get("targetNamespace")

        # Elements
        for el in root.findall(f".//{XS}element"):
            if "name" in el.attrib:
                self.elements[(tns, el.attrib["name"])] = el

        # ComplexTypes
        for ct in root.findall(f".//{XS}complexType"):
            if "name" in ct.attrib:
                name = ct.attrib["name"]
                self.types[(tns, name)] = ct

                for child in ct.findall(f".//{XS}element"):
                    name_attr = child.get("ref") or child.get("name")
                    if name_attr:
                        child_name = name_attr.split(":")[-1]
                        self.parents.setdefault(child_name, []).append(name)

        # AttributeGroups
        for ag in root.findall(f".//{XS}attributeGroup"):
            if "name" in ag.attrib:
                self.attribute_groups[(tns, ag.attrib["name"])] = ag

    # ------------------------- Element builder -------------------------
    def build_element(self, element_name, nsmap=None, attributes=None, children_attributes=None):
        tns = self.root.get("targetNamespace")
        qname = etree.QName(tns, element_name)
        if nsmap is None:
            nsmap = {k: v for k, v in (
                self.root.nsmap or {}).items() if v != XS_NS}

        el = etree.Element(qname, nsmap=nsmap)
        self._apply_element_type(
            el, (tns, element_name), attributes, children_attributes)
        return el

    def _apply_element_type(self, xml_el, key, attributes=None, children_attributes=None):
        el = self.elements.get(key)
        if el is None:
            return

        type_attr = el.get("type")  # e.g., "csw:CapabilitiesType"
        if type_attr:
            # Split prefix
            if ":" in type_attr:
                prefix, localname = type_attr.split(":")
                nsmap = self.root.nsmap
                ns = nsmap.get(prefix)
                if ns is None:
                    raise ValueError(
                        f"Unknown namespace prefix '{prefix}' in type '{type_attr}'")
            else:
                ns = self.root.get("targetNamespace")
                localname = type_attr
            # Lookup complexType by (namespace, localname)
            ct = self.types.get((ns, localname))
            if ct:
                self._apply_complex_type(
                    xml_el, ct, attributes, children_attributes)

    def _apply_complex_type(self, xml_el, ct, attributes=None, children_attributes=None):
        # complexContent/extension
        ext = ct.find(f"{XS}complexContent/{XS}extension")
        if ext is not None:
            base = ext.get("base")
            if base:
                q = etree.QName(base)
                base_ct = self.types.get((q.namespace, q.localname))
                if base_ct:
                    self._apply_complex_type(xml_el, base_ct)
            self._apply_particles_and_attrs(xml_el, ext, children_attributes)
            if attributes:
                for k, v in attributes.items():
                    if k != "_text":
                        xml_el.set(k, v)
            if attributes and "_text" in attributes:
                xml_el.text = attributes["_text"]
            return

        ext = ct.find(f"{XS}complexContent/{XS}extension")
        if ext is not None:
            base = ext.get("base")  # e.g., "ows:CapabilitiesBaseType"
            if base:
                # Resolve prefix
                if ":" in base:
                    prefix, localname = base.split(":")
                    nsmap = ct.getroottree().getroot().nsmap  # or self.root.nsmap
                    ns = nsmap.get(prefix)
                    if ns is None:
                        raise ValueError(
                            f"Unknown namespace prefix '{prefix}' in base type '{base}'")
                else:
                    ns = self.root.get("targetNamespace")
                    localname = base

                # Lookup complexType by (namespace, localname)
                base_ct = self.types.get((ns, localname))
                if base_ct is not None:
                    self._apply_complex_type(
                        xml_el, base_ct, attributes=None, children_attributes=children_attributes)

        # direct sequence/attributes
        self._apply_particles_and_attrs(xml_el, ct, children_attributes)
        if attributes and "_text" in attributes:
            xml_el.text = attributes["_text"]

    def _apply_particles_and_attrs(self, xml_el, node, attributes_map=None):
        # sequence elements
        for seq in node.findall(f"{XS}sequence"):
            for child in seq.findall(f"{XS}element"):
                mino = int(child.get("minOccurs", "1"))
                name = child.get("ref") or child.get("name")
                name_local = name.split(":")[-1]
                child_attrs = None
                if attributes_map:
                    child_attrs = attributes_map.get(name_local)
                if mino == 0 and not child_attrs:
                    continue
                occurrences = 1
                if isinstance(child_attrs, list):
                    occurrences = len(child_attrs)
                for i in range(occurrences):
                    sub_attrs = child_attrs[i] if isinstance(
                        child_attrs, list) else child_attrs
                    ns = etree.QName(child.get("ref") or child.get(
                        "name")).namespace or self.root.get("targetNamespace")
                    sub_el = etree.SubElement(
                        xml_el, etree.QName(ns, name_local))
                    type_attr = child.get("type")
                    if type_attr:
                        q = etree.QName(type_attr)
                        ct = self.types.get((q.namespace, q.localname))
                        if ct:
                            self._apply_complex_type(
                                sub_el, ct, attributes=sub_attrs, children_attributes=sub_attrs)

        # attributes
        for attr in node.findall(f"{XS}attribute"):
            xml_el.set(attr.get("name"), attr.get(
                "fixed") or attr.get("default") or "")
