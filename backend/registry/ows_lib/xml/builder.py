from importlib import resources

from lxml import etree
from registry.ows_lib.xml.consts import XSD_LOOKUP

XS_NS = "http://www.w3.org/2001/XMLSchema"
XS = f"{{{XS_NS}}}"


class XSDSkeletonBuilder:

    def __init__(self, schema_key: tuple[str, str, str]):
        self._loaded_schemas = set()
        self.elements = {}
        self.types = {}
        self.attribute_groups = {}

        try:
            xsd_filename = XSD_LOOKUP[schema_key]
        except KeyError:
            raise ValueError(f"Unsupported schema lookup: {schema_key}")

        schema_dir = resources.files("registry.ows_lib.xml.schemas")
        with schema_dir.joinpath(xsd_filename).open("rb") as f:
            xsd_bytes = f.read()

        self.root = etree.fromstring(xsd_bytes)
        self._loaded_schemas.add(self._schema_id(self.root, xsd_filename))

        self._resolve_external_schemas(self.root)
        self._index_schema(self.root)

    # ============================================================
    # Schema loading
    # ============================================================

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
                    continue

                external_root = etree.fromstring(xsd_bytes)
                schema_id = self._schema_id(external_root, schema_location)

                if schema_id in self._loaded_schemas:
                    continue

                self._loaded_schemas.add(schema_id)
                self._resolve_external_schemas(external_root)
                self._index_schema(external_root)

    def _index_schema(self, root):
        tns = root.get("targetNamespace")

        for el in root.findall(f".//{XS}element"):
            if "name" in el.attrib:
                self.elements[(tns, el.attrib["name"])] = el

        for ct in root.findall(f".//{XS}complexType"):
            if "name" in ct.attrib:
                self.types[(tns, ct.attrib["name"])] = ct

        for ag in root.findall(f".//{XS}attributeGroup"):
            if "name" in ag.attrib:
                self.attribute_groups[(tns, ag.attrib["name"])] = ag

    # ============================================================
    # QName resolution
    # ============================================================

    def _resolve_qname(self, qname_str, context_node):
        if ":" in qname_str:
            prefix, local = qname_str.split(":")
            ns = context_node.getroottree().getroot().nsmap.get(prefix)
        else:
            ns = self.root.get("targetNamespace")
            local = qname_str
        return ns, local

    # ============================================================
    # Public builder API
    # ============================================================

    def build_element(self, element_name, nsmap=None,
                      attributes=None, children_attributes=None):

        tns = self.root.get("targetNamespace")

        if nsmap is None:
            nsmap = {k: v for k, v in (self.root.nsmap or {}).items()
                     if v != XS_NS}

        el = etree.Element(etree.QName(tns, element_name), nsmap=nsmap)

        self._apply_element_type(
            el,
            (tns, element_name),
            attributes=attributes,
            children_attributes=children_attributes,
        )

        return el

    # ============================================================
    # Type handling
    # ============================================================

    def _apply_element_type(self, xml_el, key,
                            attributes=None, children_attributes=None):

        el = self.elements.get(key)
        if el is None:
            return

        type_attr = el.get("type")

        if type_attr:
            ns, local = self._resolve_qname(type_attr, el)
            ct = self.types.get((ns, local))
        else:
            ct = el.find(f"{XS}complexType")

        if ct is not None:
            self._apply_complex_type(
                xml_el,
                ct,
                attributes=attributes,
                children_attributes=children_attributes,
            )

    def _apply_complex_type(self, xml_el, ct,
                            attributes=None, children_attributes=None):

        ext = ct.find(f"{XS}complexContent/{XS}extension")
        if ext is not None:
            base = ext.get("base")
            if base:
                ns, local = self._resolve_qname(base, ext)
                base_ct = self.types.get((ns, local))
                if base_ct:
                    self._apply_complex_type(xml_el, base_ct)

            node = ext
        else:
            node = ct

        self._apply_particles_and_attrs(xml_el, node, children_attributes)

        if attributes:
            for k, v in attributes.items():
                if v is not None:
                    xml_el.set(k, str(v))

    # ============================================================
    # Core engine
    # ============================================================

    def _apply_particles_and_attrs(self, xml_el, node, children_map=None):

        # --- sequence elements ---
        for seq in node.findall(f"{XS}sequence"):
            for child in seq.findall(f"{XS}element"):

                raw_name = child.get("ref") or child.get("name")
                if not raw_name:
                    continue

                ns, local = self._resolve_qname(raw_name, child)

                child_data = None
                if children_map:
                    child_data = children_map.get(local)

                mino = int(child.get("minOccurs", "1"))
                if mino == 0 and not child_data:
                    continue

                occurrences = (
                    len(child_data)
                    if isinstance(child_data, list)
                    else 1
                )

                for i in range(occurrences):

                    data = (
                        child_data[i]
                        if isinstance(child_data, list)
                        else child_data
                    ) or {}

                    attributes = data.get("_attributes", {})
                    text = data.get("_text")

                    nested_children = {
                        k: v for k, v in data.items()
                        if k not in ("_attributes", "_text")
                    }

                    sub_el = etree.SubElement(
                        xml_el,
                        etree.QName(ns, local)
                    )

                    if text is not None:
                        sub_el.text = str(text)

                    for k, v in attributes.items():
                        if v is not None:
                            sub_el.set(k, str(v))

                    type_attr = child.get("type")
                    if type_attr:
                        tns, tlocal = self._resolve_qname(type_attr, child)
                        ct = self.types.get((tns, tlocal))
                        if ct is not None:
                            self._apply_complex_type(
                                sub_el,
                                ct,
                                attributes=None,
                                children_attributes=nested_children,
                            )

        # --- attributes defined directly ---
        for attr in node.findall(f"{XS}attribute"):
            name = attr.get("name")
            if not name or name in xml_el.attrib:
                continue

            fixed = attr.get("fixed")
            default = attr.get("default")

            if fixed is not None:
                xml_el.set(name, fixed)
            elif default is not None:
                xml_el.set(name, default)

        # --- attributeGroups ---
        for ag in node.findall(f"{XS}attributeGroup"):
            ref = ag.get("ref")
            if not ref:
                continue

            ns, local = self._resolve_qname(ref, ag)
            group = self.attribute_groups.get((ns, local))
            if group:
                self._apply_attribute_group(xml_el, group)

    def _apply_attribute_group(self, xml_el, group_node):

        for attr in group_node.findall(f"{XS}attribute"):
            name = attr.get("name")
            if not name or name in xml_el.attrib:
                continue

            fixed = attr.get("fixed")
            default = attr.get("default")

            if fixed is not None:
                xml_el.set(name, fixed)
            elif default is not None:
                xml_el.set(name, default)

        for nested in group_node.findall(f"{XS}attributeGroup"):
            ref = nested.get("ref")
            if not ref:
                continue

            ns, local = self._resolve_qname(ref, nested)
            nested_group = self.attribute_groups.get((ns, local))
            if nested_group:
                self._apply_attribute_group(xml_el, nested_group)

    def add_foreign_child(self, parent, ns, name, text=None, nsmap=None, **attrs):
        qname = etree.QName(ns, name)

        # If no parent → create new root element
        if parent is None:
            el = etree.Element(qname, nsmap=nsmap)
        else:
            el = etree.SubElement(parent, qname)

        if text is not None:
            el.text = str(text)

        for k, v in attrs.items():
            if v is not None:
                el.set(k, str(v))

        return el

    def iter(self, root, local_name=None, namespace=None):
        """
        Iterate over elements optionally filtered by local_name and/or namespace.
        """

        for el in root.iter():
            qname = etree.QName(el)

            if local_name and qname.localname != local_name:
                continue

            if namespace and qname.namespace != namespace:
                continue

            yield el


class XMLBuilder:

    def el(self, ns, local_name, parent=None, text=None, **attrs):
        element = etree.Element(etree.QName(ns, local_name)) \
            if parent is None else \
            etree.SubElement(parent, etree.QName(ns, local_name))

        if text:
            element.text = text

        for k, v in attrs.items():
            element.set(k, v)

        return element
