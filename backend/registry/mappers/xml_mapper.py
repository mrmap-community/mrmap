from pathlib import Path
from typing import IO, Union
from uuid import uuid4

from django.apps import apps
from django.core.cache import caches
from django.core.cache.backends.locmem import LocMemCache
from django.db.models import ForeignKey, ManyToManyField
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


def get_fk_field_name_from_reverse_relation(model_cls, reverse_field_name):
    """
    Gegeben: Parent-Modellklasse und Reverse-Relation-Feldname (z.B. 'layers').
    Liefert: FK-Feldname im Child-Modell, das auf Parent verweist (z.B. 'service').
    """
    ref_rel = next(field for field in model_cls._meta.related_objects if field.get_accessor_name(
    ) == reverse_field_name)
    if ref_rel:
        return ref_rel.field.name
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

    def __init__(self, xml: Union[str, Path, bytes, IO, etree._Element], mapping: dict, uuid=uuid4()):
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
        self.uuid = uuid
        if isinstance(xml, etree._Element):
            self.current_element = xml
            self.xml_root = xml.getroottree().getroot()
        else:
            # Store raw XML data as string
            self.xml_str = self._load_xml(xml)
            self.xml_root = etree.fromstring(self.xml_str)
            self.current_element = self.xml_root
        self.cache = self._get_cache()

    def _get_cache(self):
        cache = caches["local-memory"]
        if isinstance(cache, LocMemCache):
            # if this is not a local memory cache, the stored values are not immutable.
            # We need this use case here
            return cache

    def store_to_cache(self, key, value):
        if self.cache:
            unique_key = f"{self.uuid}.{key}"
            self.cache.set(unique_key, value)
            self.cache.set(self.uuid, self.cache.get(
                self.uuid, []) + [unique_key])

    def read_from_cache(self, key):
        return self.cache.get(f"{self.uuid}.{key}") if self.cache else None

    def read_all_from_cache(self):
        return self.cache.get_many(self.cache.get(f"{self.uuid}", []))

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
        """Parst ein einzelnes Feld oder Sub-Spec."""
        # Prüfen, ob das xpath_or_spec ein Sub-Spec (dict) ist
        if isinstance(xpath_or_spec, dict):
            sub_many = xpath_or_spec.get("_many", False)
            parser = self.__class__(
                xml=element, mapping=xpath_or_spec, uuid=self.uuid)
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
                return v.text if hasattr(v, "text") else str(v)
            else:
                return [v.text if hasattr(v, "text") else str(v)
                        for v in values]

    def handle_flat_field(self, field_name, instance, xml_element, xpath_or_spec, namespaces):
        # handle flat model fields
        parsed_value = self.parse_field(
            xml_element, xpath_or_spec, namespaces)
        if parsed_value is not None:
            setattr(instance, field_name, parsed_value)

    def handle_flat_fields(self, instance, xml_element, spec, namespaces):
        for field_name, xpath_or_spec in self._get_flat_fields(spec).items():
            self.handle_flat_field(
                field_name, instance, xml_element, xpath_or_spec, namespaces)

    def handle_reverse_relations(self, instance, xml_element, spec, namespaces):
        model_cls = self._get_model_class(spec)
        for rev_name, rev_spec in self._get_reverse_fields(spec).items():
            parsed = self.parse_field(xml_element, rev_spec, namespaces)
            if not parsed:
                return None

            # Standard: FK-Feld aus Reverse-Relation bestimmen
            child_parent_field = get_fk_field_name_from_reverse_relation(
                model_cls, rev_name)

            # to simplify following code and reduce code duplications
            if not isinstance(parsed, list):
                parsed = [parsed]

            for child in parsed:
                if child_parent_field:
                    setattr(child, child_parent_field, instance)

            setattr(instance, f"_{rev_spec}_parsed", parsed)

    def handle_foreign_fields(self, instance, xml_element, spec, namespaces):
        model_cls = self._get_model_class(spec)
        for field_name, xpath_or_spec in self._get_foreign_fields(spec).items():
            if isinstance(xpath_or_spec, str):
                parent = xml_element.getparent()
                candidate = xml_element.find(xpath_or_spec)
                if parent is candidate and parent.tag == candidate.tag:
                    # self reference parent/child possible
                    # if django model is self referencing too,
                    # it is a parent child tree referencing system
                    if model_cls._meta.get_field(field_name).remote_field.model == model_cls:
                        parent_path = parent.getroottree().getpath(parent)
                        parent_instance = self.read_from_cache(parent_path)
                        if parent_instance:
                            setattr(instance, field_name, parent_instance)
                else:
                    # TODO: raise valueerror or something else, cause this configuration is wrong
                    pass
            else:
                self.handle_flat_field(
                    field_name, instance, xml_element, xpath_or_spec, namespaces)

    def handle_m2m_relations(self, instance, xml_element, spec, namespaces):
        for m2m_name, m2m_spec in self._get_m2m_fields(spec).items():
            parsed = self.parse_field(xml_element, m2m_spec, namespaces)
            if not parsed:
                return None
            # to simplify following code and reduce code duplications
            if not isinstance(parsed, list):
                parsed = [parsed]
            setattr(instance, f"_{m2m_name}_parsed", parsed)

    def _get_flat_fields(self, spec):
        model_cls = self._get_model_class(spec)
        fields = spec.get("fields", {})
        return {
            key: value for key, value in fields.items()
            if key in [field.name for field in model_cls._meta.concrete_fields
                       if not isinstance(field, ForeignKey)]
        }

    def _get_reverse_fields(self, spec):
        model_cls = self._get_model_class(spec)
        fields = spec.get("fields", {})
        return {
            key: value for key, value in fields.items()
            if key in [rel.get_accessor_name() for rel in model_cls._meta.related_objects]
        }

    def _get_foreign_fields(self, spec):
        model_cls = self._get_model_class(spec)
        fields = spec.get("fields", {})
        return {
            key: value for key, value in fields.items()
            if key in [field.name for field in model_cls._meta.concrete_fields
                       if isinstance(field, ForeignKey)]
        }

    def _get_m2m_fields(self, spec):
        model_cls = self._get_model_class(spec)
        fields = spec.get("fields", {})
        return {
            key: value for key, value in fields.items()
            if key in [m2m.name for m2m in model_cls._meta.local_many_to_many]
        }

    def _get_elements(self, spec, namespaces):
        base_xpath = spec.get("_base_xpath", ".")
        return (
            self.current_element.xpath(base_xpath, namespaces=namespaces)
            if base_xpath else [self.current_element]
        )

    def _get_model_class(self, spec):
        model_label = spec.get("_model")
        if not model_label:
            raise ValueError("Spec missing _model")
        return apps.get_model(model_label)

    def traverse_spec(
        self,
        spec,
        namespaces=None,
        many=False,
    ):
        """Traversiert ein Mapping-Spec, inkl. Baumstruktur und Reverse-Relations."""
        many = spec.get("_many", many)
        model_cls = self._get_model_class(spec)

        elements = self._get_elements(spec, namespaces)

        instances = [] if many else None

        for el in elements:
            path = el.getroottree().getpath(el)
            instance = model_cls()

            self.handle_flat_fields(instance, el, spec, namespaces)
            self.handle_foreign_fields(instance, el, spec, namespaces)
            self.handle_reverse_relations(instance, el, spec, namespaces)
            self.handle_m2m_relations(instance, el, spec, namespaces)

            if many:
                instances.append(instance)
            else:
                instances = instance

            self.store_to_cache(path, instance)
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
