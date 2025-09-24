from pathlib import Path
from typing import IO, Union

from django.apps import apps
from django.db.models import ManyToManyField
from lxml import etree

# -------------------------------------------------------------------
# Utilities
# -------------------------------------------------------------------


def get_model_class(label: str):
    """Lädt eine Modelklasse anhand von app_label.ModelName"""
    return apps.get_model(label)


def load_function(path: str):
    """Importiert eine Funktion aus einem string 'module.func'"""
    mod_name, func_name = path.rsplit(".", 1)
    mod = __import__(mod_name, fromlist=[func_name])
    return getattr(mod, func_name)


def _get_value(res):
    if not res:
        return None
    node = res[0]
    if hasattr(node, "text"):
        return node.text
    return str(node)


class XmlMapper:

    def __init__(self, xml: Union[str, Path, bytes, IO], mapping: dict):
        """
        Initialize XmlMapper.

        Args:
            xml (str | Path | bytes | IO): XML source, can be:
                - str (XML string or file path)
                - Path (path to XML file)
                - bytes (XML content)
                - IO (open file-like object)
            mapping (dict): mapping configuration dictionary.
        """
        self.mapping = mapping

        # Store raw XML data as string
        self.xml_str = self._load_xml(xml)
        self.xml_root = etree.fromstring(self.xml_str)

    def _load_xml(self, xml: Union[str, Path, bytes, IO]) -> bytes:
        """Normalize different input types to raw XML bytes for lxml."""
        if isinstance(xml, etree._ElementTree):
            return etree.tostring(xml.getroot())

        elif isinstance(xml, etree._Element):
            return etree.tostring(xml)

        elif isinstance(xml, Path):
            return xml.read_bytes()

        elif isinstance(xml, str):
            # Heuristik: check if this is a filesystem path
            p = Path(xml)
            if p.exists():
                return p.read_bytes()
            return xml.encode("utf-8")  # interpret str as direct XML source

        elif isinstance(xml, bytes):
            return xml

        elif hasattr(xml, "read"):
            content = xml.read()
            return content if isinstance(content, bytes) else content.encode("utf-8")

        else:
            raise TypeError(f"Unsupported XML input type: {type(xml)}")

    def traverse_spec(self, spec, namespaces=None, many=False):
        base_xpath = spec.get("_base_xpath", "")
        fields = spec.get("fields", {})
        many = spec.get("_many", many)
        model_cls = get_model_class(spec["_model"])

        elements = (
            self.xml_root.xpath(base_xpath, namespaces=namespaces)
            if base_xpath else [self.xml_root]
        )
        if not elements:
            return [] if many else None

        instances = [] if many else None

        for el in elements:
            data = {}
            m2m_temp = {}

            for field_name, xpath_or_spec in fields.items():
                field_obj = model_cls._meta.get_field(field_name)

                if isinstance(xpath_or_spec, dict):
                    sub_many = xpath_or_spec.get("_many", False)
                    parser = self.__class__(xml=el, mapping=xpath_or_spec)
                    parsed = parser.traverse_spec(
                        xpath_or_spec, namespaces, many=sub_many)

                    if isinstance(field_obj, ManyToManyField):
                        m2m_temp[field_name] = parsed
                    else:
                        data[field_name] = parsed
                else:
                    values = el.xpath(xpath_or_spec, namespaces=namespaces)
                    if not values:
                        data[field_name] = None
                    elif len(values) == 1:
                        data[field_name] = _get_value(values[0])
                    else:
                        data[field_name] = [_get_value(v) for v in values]

            # Hauptinstanz bauen (ManyToMany noch nicht setzen!)
            instance = model_cls(**data)

            # temporär ManyToMany speichern
            for k, v in m2m_temp.items():
                setattr(instance, f"_{k}_parsed", v)

            if many:
                instances.append(instance)
            else:
                instances = instance

        return instances

    def xml_to_django(self):
        namespaces = self.mapping.get("_namespaces", None)

        data = []
        for key, value in self.mapping.items():
            if key.startswith("_"):
                continue
            instance = self.traverse_spec(value, namespaces)
            if instance:
                data.append(instance)

        return data
        return data
