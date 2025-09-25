from pathlib import Path
from typing import IO, Union

from django.apps import apps
from django.db.models import ManyToManyField
from django.db.models.fields.reverse_related import ManyToManyRel, ManyToOneRel
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


def get_fk_field_name_from_reverse_relation(parent_model_cls, reverse_field_name):
    """
    Gegeben: Parent-Modellklasse und Reverse-Relation-Feldname (z.B. 'layers').
    Liefert: FK-Feldname im Child-Modell, das auf Parent verweist (z.B. 'service').
    """
    try:
        reverse_field = parent_model_cls._meta.get_field(reverse_field_name)
    except Exception:
        return None

    # Reverse-Relation hat related_model (Child)
    child_model_cls = getattr(reverse_field, "related_model", None)
    if child_model_cls is None:
        return None

    # Suche FK-Feld im Child, das auf Parent verweist
    for f in child_model_cls._meta.get_fields():
        if f.is_relation and f.related_model == parent_model_cls:
            return f.name

    return None


def set_parent_fk_on_instances(instances, fk_field_name, parent_instance):
    if not fk_field_name or not parent_instance or not instances:
        return

    if isinstance(instances, list):
        for inst in instances:
            setattr(inst, fk_field_name, parent_instance)
    else:
        setattr(instances, fk_field_name, parent_instance)


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

    def parse_field(
        self,
        element,
        xpath_or_spec,
        namespaces
    ):
        """
        Parst ein einzelnes Feld, kann rekursiv aufrufen bei Sub-Specs.
        Liefert (parsed_value, is_many_to_many_flag) zurück.
        """
        # Prüfen, ob das xpath_or_spec ein Sub-Spec (dict) ist
        if isinstance(xpath_or_spec, dict):
            sub_many = xpath_or_spec.get("_many", False)
            parser = self.__class__(xml=element, mapping=xpath_or_spec)
            parsed = parser.traverse_spec(
                xpath_or_spec,
                namespaces,
                many=sub_many
            )
            return parsed

        else:
            # Einfache XPath-Auswertung
            values = element.xpath(xpath_or_spec, namespaces=namespaces)
            if not values:
                return None
            elif len(values) == 1:
                v = values[0]
                val = v.text if hasattr(v, "text") else str(v)
                return val
            else:
                vals = [v.text if hasattr(v, "text") else str(v)
                        for v in values]
                return vals

    def traverse_spec(
        self,
        spec,
        namespaces=None,
        many=False
    ):

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

        # Feld-Kategorien holen
        concrete_field_names = {
            f.name for f in model_cls._meta.concrete_fields}
        reverse_relation_names = {
            rel.get_accessor_name(): rel for rel in model_cls._meta.related_objects}

        for el in elements:
            instance = model_cls()
            data = {}
            m2m_temp = {}

            for field_name, xpath_or_spec in fields.items():
                parsed_value = self.parse_field(
                    el,
                    xpath_or_spec,
                    namespaces
                )

                if field_name in concrete_field_names:
                    data[field_name] = parsed_value
                elif field_name in reverse_relation_names:
                    if isinstance(reverse_relation_names[field_name], ManyToOneRel):
                        # this is a FK on the child model. So we need to set the current instance (parent) on the child
                        setattr(
                            parsed_value[0], reverse_relation_names[field_name].remote_field.name, instance)

                    m2m_temp[field_name] = parsed_value
                else:
                    print(
                        f"Warnung: Feld '{field_name}' nicht gefunden im Model {model_cls.__name__}")

            for k, v in data.items():
                setattr(instance, k, v)

            # Temporär die Reverse Relations anhängen (für späteres Speichern)
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
