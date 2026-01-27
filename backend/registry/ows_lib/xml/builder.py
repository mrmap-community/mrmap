from importlib import resources

from lxml import etree
from registry.ows_lib.xml.consts import XSD_LOOKUP

XS_NS = "http://www.w3.org/2001/XMLSchema"
XS = f"{{{XS_NS}}}"


class XSDSkeletonBuilder:

    def __init__(self, xsd: bytes | tuple[str, str, str]):
        # child_name -> list of (parent_element_name, complexType)
        self.parents = {}
        # Load XSD bytes
        if isinstance(xsd, tuple):
            try:
                xsd_filename = XSD_LOOKUP[xsd]
            except KeyError:
                raise ValueError(f"Unsupported XSD lookup: {xsd}")
            with resources.files("registry.ows_lib.xml.schemas").joinpath(xsd_filename).open("rb") as f:
                xsd = f.read()

        self.tree = etree.fromstring(xsd)
        self.root = self.tree.getroottree().getroot()

        self.elements = {}
        self.types = {}
        self.attribute_groups = {}

        self._index_schema()

    def _index_schema(self):
        for el in self.root.findall(f".//{XS}element"):
            if "name" in el.attrib:
                self.elements[el.attrib["name"]] = el

        for ct in self.root.findall(f".//{XS}complexType"):
            if "name" in ct.attrib:
                self.types[ct.attrib["name"]] = ct

                for child in ct.findall(f".//{XS}element"):
                    name = child.get("ref") or child.get("name")
                    if name:
                        child_name = name.split(":")[-1]
                        self.parents.setdefault(
                            child_name, []).append(ct.attrib["name"])

        for ag in self.root.findall(f".//{XS}attributeGroup"):
            if "name" in ag.attrib:
                self.attribute_groups[ag.attrib["name"]] = ag

    def _find_element_path(self, element_name):
        """
        Returns a list like: [Root, ..., Parent, element_name]
        """
        visited = set()

        def dfs(name):
            if name in visited:
                return None
            visited.add(name)

            # root element
            if name in self.elements and self.elements[name].get("type"):
                return [name]

            for parent_type in self.parents.get(name, []):
                for el_name, el in self.elements.items():
                    if el.get("type", "").endswith(parent_type):
                        path = dfs(el_name)
                        if path:
                            return path + [name]
            return None

        return dfs(element_name)

    def iter(self, xml: etree._Element, local_name: str | None = None):
        """
        Iterate over all descendants (or children) optionally filtered by local-name.

        :param parent: the element to iterate over, defaults to root if None
        :param local_name: optional local-name to filter elements
        :yield: etree._Element
        """
        if xml is None:
            return  # nothing to iterate

        for el in xml.iter():
            if local_name is None or etree.QName(el).localname == local_name:
                yield el

    def build_deep_element(
        self,
        element_name,
        nsmap=None,
        attributes=None,
    ):
        path = self._find_element_path(element_name)
        if not path:
            raise ValueError(
                f"No valid path found for element '{element_name}'")

        root_name = path[0]
        root = self.build_element(root_name, nsmap=nsmap)

        current = root
        for name in path[1:]:
            current = self._ensure_child(current, name)

        # apply attributes/text only to target
        if attributes:
            for k, v in attributes.items():
                if k == "_text":
                    current.text = v
                else:
                    current.set(k, v)

        return root

    def _ensure_child(self, parent, child_name):
        # already exists
        for c in parent:
            if etree.QName(c).localname == child_name:
                return c

        child = etree.SubElement(parent, self._element_qname(child_name))
        self._apply_element_type(child, child_name)
        return child

    # -------------------- Helper functions --------------------
    def _schema_nsmap(self):
        return {k: v for k, v in (self.root.nsmap or {}).items() if v != XS_NS}

    def _element_qname(self, element_name):
        tns = self.root.get("targetNamespace")
        if tns:
            return etree.QName(tns, element_name)
        return element_name

    def _attribute_value(self, attr):
        if "fixed" in attr.attrib:
            return attr.get("fixed")
        if "default" in attr.attrib:
            return attr.get("default")
        t = attr.get("type", "")
        if t.endswith("boolean"):
            return "false"
        if t.endswith(("integer", "decimal")):
            return "0"
        if "date" in t:
            return "1970-01-01T00:00:00Z"

    # -------------------- Core builder functions --------------------
    def _apply_element_type(self, xml_el, element_name, attributes=None, children_attributes=None):
        xsd_el = self.elements[element_name]
        type_name = xsd_el.get("type")
        if type_name:
            type_name = type_name.split(":")[-1]
            ct = self.types.get(type_name)
            if ct is not None:
                self._apply_complex_type(
                    xml_el, ct, attributes=attributes, children_attributes=children_attributes)

    def _apply_complex_type(self, xml_el, ct, attributes=None, children_attributes=None):
        # simpleContent / extension
        ext = ct.find(f"{XS}simpleContent/{XS}extension")
        if ext is not None:
            # Set text from attributes if provided, else default
            if attributes and "_text" in attributes:
                xml_el.text = attributes["_text"]

            for attr in ext.findall(f"{XS}attribute"):
                if attr.get("use") == "prohibited":
                    continue
                attr_value = self._attribute_value(attr)
                if attr_value:
                    xml_el.set(attr.get("name"), attr_value)
            if attributes:
                for k, v in attributes.items():
                    if k != "_text":  # don't override text here
                        xml_el.set(k, v)
            return

        # complexContent / extension
        ext = ct.find(f"{XS}complexContent/{XS}extension")
        if ext is not None:
            base = ext.get("base")
            if base:
                base_name = base.split(":")[-1]
                base_ct = self.types.get(base_name)
                if base_ct is not None:
                    self._apply_complex_type(
                        xml_el, base_ct, attributes=attributes, children_attributes=children_attributes)
            self._apply_particles_and_attrs(
                xml_el, ext, attributes_map=children_attributes)
            if attributes:
                for k, v in attributes.items():
                    if k != "_text":
                        xml_el.set(k, v)
            return

        # direct sequence / attributes
        self._apply_particles_and_attrs(
            xml_el, ct, attributes_map=children_attributes)
        if attributes:
            for k, v in attributes.items():
                if k != "_text":
                    xml_el.set(k, v)

    def _apply_particles_and_attrs(self, xml_el, node, attributes_map=None):
        # sequence
        seq = node.find(f"{XS}sequence")
        if seq is not None:
            for child in seq.findall(f"{XS}element"):
                mino = int(child.get("minOccurs", "1"))
                # create child if required or if attributes provided
                create = mino > 0 or (
                    attributes_map and child.get("name") in attributes_map)
                if create:
                    name = child.get("ref") or child.get("name")
                    name_local = name.split(":")[-1]
                    child_xml = etree.SubElement(
                        xml_el, self._element_qname(name_local))
                    child_attrs = attributes_map.get(
                        name_local) if attributes_map else None
                    type_name = child.get("type")
                    if type_name:
                        type_name = type_name.split(":")[-1]
                        ct = self.types.get(type_name)
                        if ct is not None:
                            self._apply_complex_type(
                                child_xml,
                                ct,
                                attributes=child_attrs,
                                children_attributes=None
                            )

        # attributeGroup
        for ag in node.findall(f"{XS}attributeGroup"):
            ref = ag.get("ref").split(":")[-1]
            self._apply_attribute_group(xml_el, ref)

        # attributes
        for attr in node.findall(f"{XS}attribute"):
            if attr.get("use") == "prohibited":
                continue
            xml_el.set(attr.get("name"), self._attribute_value(attr))

    def _apply_attribute_group(self, xml_el, group_name):
        ag = self.attribute_groups.get(group_name)
        if ag is None:
            return
        for attr in ag.findall(f"{XS}attribute"):
            if attr.get("use") == "required" or "default" in attr.attrib or "fixed" in attr.attrib:
                xml_el.set(attr.get("name"), self._attribute_value(attr))

    # -------------------- Public builder --------------------
    def build_element(self, element_name, nsmap=None, attributes=None, children_attributes=None):
        xsd_el = self.elements[element_name]

        if nsmap is None:
            nsmap = self._schema_nsmap() or None

        qname = self._element_qname(element_name)
        xml_el = etree.Element(qname, nsmap=nsmap)

        # Apply type + attributes
        # 1. Named type
        type_name = xsd_el.get("type")
        if type_name:
            type_name = type_name.split(":")[-1]
            ct = self.types.get(type_name)
            if ct is not None:
                self._apply_complex_type(
                    xml_el, ct,
                    attributes=attributes,
                    children_attributes=children_attributes
                )
        # 2. Anonymous complexType
        else:
            ct = xsd_el.find(f"{XS}complexType")
            if ct is not None:
                self._apply_complex_type(
                    xml_el, ct,
                    attributes=attributes,
                    children_attributes=children_attributes
                )

        # Apply attributes directly on element (if no type)
        if attributes:
            for k, v in attributes.items():
                if k != "_text":
                    xml_el.set(k, v)
            if "_text" in attributes:
                xml_el.text = attributes["_text"]

        return xml_el

    def add_child_element(self, parent, child_name, attributes=None):
        child = etree.SubElement(parent, self._element_qname(child_name))
        self._apply_element_type(child, child_name, attributes=attributes)
        return child

    def ensure_element(self, parent, name):
        """
        Ensure a child element exists (do not duplicate).
        """
        for child in parent:
            if etree.QName(child).localname == name:
                return child

        child = etree.SubElement(parent, self._element_qname(name))
        self._apply_element_type(child, name)
        return child

    def set_required_attributes(self, el, type_name):
        """
        Apply required/default/fixed attributes for a complexType.
        """
        ct = self.types.get(type_name)
        if not ct:
            return

        self._apply_complex_type(el, ct)

    def add_foreign_child(
        self,
        parent,
        qname: etree.QName,
        text=None,
        attributes=None,
    ):
        """
        Add an element not defined in the active XSD
        (e.g. ogc:Filter, gml:Envelope)
        """
        if parent is None:
            el = etree.Element(qname)
        else:
            el = etree.SubElement(parent, qname)

        if attributes:
            for k, v in attributes.items():
                el.set(k, v)
        if text is not None:
            el.text = text
        return el
