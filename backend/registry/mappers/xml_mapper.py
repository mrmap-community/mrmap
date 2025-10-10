import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import IO, Union
from uuid import uuid4

from django.apps import apps
from django.db.models import ForeignKey
from lxml import etree
from registry.mappers.configs import XPATH_MAP

# -------------------------------------------------------------------
# Cache
# -------------------------------------------------------------------


class GlobalXmlCache:
    """Threadsicherer Cache mit TTL und automatischem Hintergrund-Cleanup."""
    _lock = threading.RLock()
    _data = OrderedDict()  # key -> (value, expire_time)
    _ttl_seconds = 3600  # 1 Stunde TTL
    _cleanup_interval = 300  # Alle 5 Minuten cleanup durchführen

    _cleanup_thread = None
    _stop_event = threading.Event()

    @classmethod
    def _start_cleanup_thread(cls):
        if cls._cleanup_thread is None or not cls._cleanup_thread.is_alive():
            cls._stop_event.clear()
            cls._cleanup_thread = threading.Thread(
                target=cls._cleanup_loop, daemon=True)
            cls._cleanup_thread.start()

    @classmethod
    def _cleanup_loop(cls):
        while not cls._stop_event.wait(cls._cleanup_interval):
            cls._cleanup_expired_locked()

    @classmethod
    def stop_cleanup_thread(cls):
        """Stoppt den Hintergrund-Cleanup-Thread (z.B. beim Programmende)."""
        cls._stop_event.set()
        if cls._cleanup_thread:
            cls._cleanup_thread.join()

    @classmethod
    def set(cls, key, value):
        expire_at = time.time() + cls._ttl_seconds
        with cls._lock:
            cls._data[key] = (value, expire_at)
            cls._data.move_to_end(key)
        cls._start_cleanup_thread()

    @classmethod
    def get(cls, key, default=None):
        now = time.time()
        with cls._lock:
            item = cls._data.get(key)
            if item is None:
                return default
            value, expire_at = item
            if expire_at < now:
                del cls._data[key]
                return default
            # Key frisch halten, falls gewünscht (z.B. LRU-Verhalten)
            cls._data.move_to_end(key)
            return value

    @classmethod
    def get_many(cls, keys):
        now = time.time()
        result = OrderedDict()
        with cls._lock:
            for key in keys:
                item = cls._data.get(key)
                if item is None:
                    result[key] = None
                    continue
                value, expire_at = item
                if expire_at < now:
                    del cls._data[key]
                    result[key] = None
                else:
                    cls._data.move_to_end(key)
                    result[key] = value
        return result

    @classmethod
    def add_to_list(cls, key, value):
        with cls._lock:
            item = cls._data.get(key)
            now = time.time()
            expire_at = now + cls._ttl_seconds

            if item is None or item[1] < now:
                # Wenn Schlüssel nicht existiert oder abgelaufen, neuen Eintrag mit Liste starten
                cls._data[key] = ([value], expire_at)
            else:
                lst, expire_at = item
                lst.append(value)
                cls._data[key] = (lst, expire_at)
            cls._data.move_to_end(key)

    @classmethod
    def clear(cls):
        with cls._lock:
            cls._data.clear()

    @classmethod
    def _cleanup_expired_locked(cls):
        """Entfernt abgelaufene Einträge. Muss mit Lock gehalten aufgerufen werden."""
        now = time.time()
        keys_to_delete = [k for k, (_, expire_at)
                          in cls._data.items() if expire_at < now]
        for k in keys_to_delete:
            del cls._data[k]

# -------------------------------------------------------------------
# Utilities
# -------------------------------------------------------------------


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


def load_file(xml: Union[str, Path, bytes, IO]) -> bytes:
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


class XmlMapper:

    def __init__(
        self,
        xml: Union[str, Path, bytes, IO, etree._Element],
        mapping: dict,
        uuid=None
    ):
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
        if uuid is None:
            uuid = uuid4()
        self.uuid = uuid
        if isinstance(xml, etree._Element):
            self.current_element = xml
            self.xml_root = xml.getroottree().getroot()
        else:
            # Store raw XML data as string
            self.xml_str = load_file(xml)
            self.xml_root = etree.fromstring(self.xml_str)
            self.current_element = self.xml_root
        self.cache = GlobalXmlCache

    def store_to_cache(self, key, value):
        unique_key = f"{self.uuid}:{key}"
        self.cache.set(unique_key, value)
        self.cache.add_to_list(self.uuid, unique_key)

    def read_from_cache(self, key):
        return self.cache.get(f"{self.uuid}:{key}")

    def read_all_from_cache(self):
        all_keys = self.cache.get(self.uuid, [])
        return self.cache.get_many(all_keys)

    def get_element_path(self, element):
        return element.getroottree().getpath(element)

    def get_instance_by_element(self, element):
        return self.read_from_cache(self.get_element_path(element))

    def parse_field(
        self,
        element,
        xpath_or_spec,
        namespaces
    ):
        """Parst ein einzelnes Feld oder Sub-Spec."""
        # Prüfen, ob das xpath_or_spec ein Sub-Spec (dict) ist
        if isinstance(xpath_or_spec, dict) and "_model" in xpath_or_spec:
            sub_many = xpath_or_spec.get("_many", False)
            parser = self.__class__(
                xml=element,
                mapping=xpath_or_spec | {
                    "_namespaces": self.mapping.get("_namespaces", {})},
                uuid=self.uuid
            )
            parsed = parser.traverse_spec(
                xpath_or_spec,
                namespaces,
                many=sub_many
            )
            return parsed
        elif isinstance(xpath_or_spec, dict) and "_inputs" in xpath_or_spec and "_parser" in xpath_or_spec:
            values = []
            for xpath_expr in xpath_or_spec["_inputs"]:
                res = element.xpath(xpath_expr, namespaces=namespaces)
                if not res:
                    values.append(xpath_or_spec.get("_default", None))
                else:
                    # Ob Attribut oder Elementtext
                    node = res[0]
                    if isinstance(node, etree._ElementUnicodeResult):
                        # Wenn Attribut oder direkte Text
                        values.append(str(node))
                    elif hasattr(node, "text"):
                        values.append(node.text)
                    else:
                        values.append(str(node))
            parser_func = load_function(xpath_or_spec["_parser"])
            try:
                parsed = parser_func(self, *values)
            except Exception as e:
                # Logging oder Fallback
                parsed = None
            finally:
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
                # no elements parsed. continue with next reverse field
                continue

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
                candidate = xml_element.find(
                    xpath_or_spec, namespaces=namespaces)
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
                # no instances created... continue with the next m2m field
                continue
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
        instances = [] if many else None
        elements = self._get_elements(spec, namespaces)

        if "_parser" in spec:
            parser = load_function(spec.get("_parser"))

            for el in elements:
                path = el.getroottree().getpath(el)
                instance = parser(self, el)
                if isinstance(instance, list):
                    instances.extend(instance)
                    for idx, inst in enumerate(instance):
                        self.store_to_cache(f"{path}_{idx}", inst)
                else:
                    instances = instance
                    self.store_to_cache(path, instance)

            return instances

        else:
            model_cls = self._get_model_class(spec)

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


class OGCServiceXmlMapper(XmlMapper):

    @classmethod
    def from_xml(cls, xml):
        # Root-Element extrahieren
        content = load_file(xml)
        root = etree.fromstring(content)

        # Service-Typ anhand des Root-Tags
        tag = etree.QName(root).localname.lower()
        if "wms" or "wmt" in tag:
            service_type = "WMS"
        elif "wfs" in tag:
            service_type = "WFS"
        elif "capabilities" in tag and "csw" in root.nsmap.values():
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
