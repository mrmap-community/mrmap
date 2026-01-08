from lxml import etree

XS_NS = "http://www.w3.org/2001/XMLSchema"
XS = f"{{{XS_NS}}}"


class XSDSkeletonBuilder:
    def __init__(self, xsd: bytes):
        self.tree = etree.fromstring(xsd)
        self.root = self.tree.getroot()

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

        for ag in self.root.findall(f".//{XS}attributeGroup"):
            if "name" in ag.attrib:
                self.attribute_groups[ag.attrib["name"]] = ag

    def _default_value(self, attr):
        t = attr.get("type", "")
        if t.endswith("boolean"):
            return "false"
        if t.endswith("integer") or t.endswith("decimal"):
            return "0"
        if "date" in t:
            return "1970-01-01T00:00:00Z"
        return "VALUE"

    def _apply_attribute_group(self, xml_el, group_name):
        ag = self.attribute_groups.get(group_name)
        if ag is None:
            return

        for attr in ag.findall(f"{XS}attribute"):
            if attr.get("use") == "required" or "default" in attr.attrib:
                xml_el.set(
                    attr.get("name"),
                    attr.get("default", self._default_value(attr))
                )

    def _apply_element_type(self, xml_el, element_name):
        xsd_el = self.elements[element_name]
        type_name = xsd_el.get("type")
        if type_name:
            type_name = type_name.split(":")[-1]
            ct = self.types.get(type_name)
            if ct is not None:
                self._apply_complex_type(xml_el, ct)

    def _apply_particles_and_attrs(self, xml_el, node):
        # sequence
        seq = node.find(f"{XS}sequence")
        if seq is not None:
            for child in seq.findall(f"{XS}element"):
                mino = int(child.get("minOccurs", "1"))
                if mino > 0:
                    name = child.get("ref") or child.get("name")
                    name = name.split(":")[-1]
                    child_xml = etree.SubElement(xml_el, name)
                    # Rekursion
                    if name in self.elements:
                        self._apply_element_type(child_xml, name)

        # attributeGroup
        for ag in node.findall(f"{XS}attributeGroup"):
            ref = ag.get("ref").split(":")[-1]
            self._apply_attribute_group(xml_el, ref)

        # attributes
        for attr in node.findall(f"{XS}attribute"):
            if attr.get("use") == "required":
                xml_el.set(attr.get("name"), self._default_value(attr))

    def _apply_complex_type(self, xml_el, ct):
        # complexContent / extension
        ext = ct.find(f"{XS}complexContent/{XS}extension")
        if ext is not None:
            base = ext.get("base")
            if base:
                base_name = base.split(":")[-1]
                base_ct = self.types.get(base_name)
                if base_ct is not None:
                    self._apply_complex_type(xml_el, base_ct)
            self._apply_particles_and_attrs(xml_el, ext)
            return

        # direkt sequence / attributes
        self._apply_particles_and_attrs(xml_el, ct)

    def build_element(self, element_name, nsmap=None):
        xsd_el = self.elements[element_name]
        xml_el = etree.Element(element_name, nsmap=nsmap)

        # type → complexType
        type_name = xsd_el.get("type")
        if type_name:
            type_name = type_name.split(":")[-1]
            ct = self.types.get(type_name)
            if ct is not None:
                self._apply_complex_type(xml_el, ct)

        return xml_el
