import logging
from pathlib import Path
from typing import IO, Union
from uuid import uuid4

from django.apps import apps
from django.core.exceptions import ImproperlyConfigured, ObjectDoesNotExist
from django.db.models import ForeignKey, Model
from lxml import etree
from registry import models
from registry.mappers.cache import GlobalXmlCache
from registry.mappers.utils import (compose_xpath,
                                    get_fk_field_name_from_reverse_relation,
                                    is_editable_concrete_field,
                                    is_many_relation, load_file, load_function,
                                    normalize_predicate_xpath, xpath_literal)

from .xpath import util
from .xpath.core import parse


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
        self.data = []

    def serialize_document(
        self,
        pretty_print: bool = True,
        xml_declaration: bool = True,
        encoding: str = "utf-8"
    ) -> bytes:
        """
        Serializes self.xml_root as a complete XML document.

        Args:
            pretty_print (bool): Pretty-print the XML.
            xml_declaration (bool): Include XML declaration.
            encoding (str): Output encoding.

        Returns:
            bytes: Serialized XML document.
        """
        return etree.tostring(
            self.xml_root,
            pretty_print=pretty_print,
            xml_declaration=xml_declaration,
            encoding=encoding
        )

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
        if isinstance(element, etree._ElementUnicodeResult):
            parent = element.getparent()
            path = f"{parent.getroottree().getpath(parent)}/text()"
        else:
            path = element.getroottree().getpath(element)
        return path

    def get_instance_by_element(self, element):
        return self.read_from_cache(self.get_element_path(element))

    def parse_field(
        self,
        element,
        xpath_or_spec,
        namespaces,
        is_many: bool = False
    ):
        """Parst ein einzelnes Feld oder Sub-Spec."""
        # Prüfen, ob das xpath_or_spec ein Sub-Spec (dict) ist
        if isinstance(xpath_or_spec, dict) and "_model" in xpath_or_spec:
            parser = self.__class__(
                xml=element,
                mapping=xpath_or_spec | {
                    "_namespaces": self.mapping.get("_namespaces", {})},
                uuid=self.uuid
            )
            parsed = parser.traverse_spec(
                xpath_or_spec,
                namespaces,
                is_many=is_many
            )
            return parsed
        elif isinstance(xpath_or_spec, dict) and "_inputs" in xpath_or_spec and "_parser" in xpath_or_spec:
            values = []
            for xpath_expr in xpath_or_spec["_inputs"]:
                try:
                    res = element.xpath(xpath_expr, namespaces=namespaces)
                except etree.XPathEvalError as e:
                    logging.error(
                        f"Error parsing field with xpath '{xpath_expr}': {e}"
                    )
                if not res:
                    logging.debug(
                        f"No result by xpath '{xpath_expr}'. Fallback _default is used.")
                    values.append(xpath_or_spec.get("_default", None))
                else:
                    # Ob Attribut oder Elementtext
                    node = res[0]
                    values.append(node)
            parser_func = load_function(xpath_or_spec["_parser"])
            try:
                parsed = parser_func(self, *values)
                if parsed is None:
                    logging.debug(
                        f"{xpath_or_spec["_parser"]} does return None with args: {values}")
            except Exception as e:
                logging.error(
                    f"Error parsing field with function {xpath_or_spec['_parser']} with args: {values}: {e}")
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
            # Standard: FK-Feld aus Reverse-Relation bestimmen
            child_parent_field = get_fk_field_name_from_reverse_relation(
                model_cls, rev_name)

            is_many = is_many_relation(model_cls, rev_name)

            parsed = self.parse_field(
                xml_element, rev_spec, namespaces, is_many)
            if not parsed:
                # no elements parsed. continue with next reverse field
                continue

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
                # this is an xpath... this is only possible for parent/child (self) related fields
                if not model_cls._meta.get_field(field_name).remote_field.model == model_cls:
                    raise ImproperlyConfigured(
                        f'field {field_name} does not reverence to it self')
                # self reference parent/child possible
                # if django model is self referencing too,
                # it is a parent child tree referencing system
                parent = xml_element.getparent()

                candidate = xml_element.find(
                    xpath_or_spec, namespaces=namespaces)
                if parent is candidate and parent.tag == candidate.tag:
                    parent_path = parent.getroottree().getpath(parent)
                    parent_instance = self.read_from_cache(parent_path)
                    if parent_instance:
                        setattr(instance, field_name, parent_instance)
            else:
                self.handle_flat_field(
                    field_name, instance, xml_element, xpath_or_spec, namespaces)

    def handle_m2m_relations(self, instance, xml_element, spec, namespaces):
        for m2m_name, m2m_spec in self._get_m2m_fields(spec).items():
            parsed = self.parse_field(
                xml_element, m2m_spec, namespaces, is_many=True)
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

    def compile_concrete_xpath(self, instance, spec):
        """
        Fully spec-driven concrete XPath builder.

        WARNING:
        This XPath is instance-specific and must NOT be persisted.
        It is derived from spec + instance state.

        """

        base_xpath = spec["_base_xpath"]
        predicates = []

        flat_fields = self._get_flat_fields(spec)
        parent_xpath = None

        for field_name, xpath_or_spec in flat_fields.items():
            if is_editable_concrete_field(instance, field_name):
                continue

            value = getattr(instance, field_name, None)
            if value in (None, "", []):
                continue

            # Parent handling
            if xpath_or_spec == "..":
                parent_xpath = self.compile_concrete_xpath(value, spec)
                continue

            # Simple xpath
            if isinstance(xpath_or_spec, str):
                predicate_xpath = normalize_predicate_xpath(xpath_or_spec)
                if predicate_xpath:
                    predicates.append(
                        f"{predicate_xpath}={xpath_literal(str(value))}"
                    )

            # Complex xpath
            elif isinstance(xpath_or_spec, dict):
                for input_xpath in xpath_or_spec.get("_inputs", ()):
                    predicate_xpath = normalize_predicate_xpath(input_xpath)
                    if predicate_xpath:
                        predicates.append(
                            f"{predicate_xpath}={xpath_literal(str(value))}"
                        )

        # Compose xpath generically
        if parent_xpath:
            concrete_xpath = compose_xpath(parent_xpath, base_xpath)
        else:
            concrete_xpath = base_xpath

        if predicates:
            concrete_xpath += "[" + " and ".join(predicates) + "]"

        return concrete_xpath

    def traverse_spec(
        self,
        spec,
        namespaces=None,
        is_many: bool = False
    ):
        """Traversiert ein Mapping-Spec, inkl. Baumstruktur und Reverse-Relations."""

        instances = [] if is_many else None
        elements = self._get_elements(spec, namespaces)
        if "_parser" in spec:
            parser = load_function(spec.get("_parser"))

            for el in elements:
                path = self.get_element_path(el)
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
                path = self.get_element_path(el)
                instance = model_cls()

                self.handle_flat_fields(instance, el, spec, namespaces)
                self.handle_foreign_fields(instance, el, spec, namespaces)
                self.handle_reverse_relations(instance, el, spec, namespaces)
                self.handle_m2m_relations(instance, el, spec, namespaces)

                if is_many:
                    instances.append(instance)
                else:
                    instances = instance

                self.store_to_cache(path, instance)
            return instances

    def xml_to_django(self):
        namespaces = self.mapping.get("_namespaces", None)

        for key, value in self.mapping.items():
            if key.startswith("_"):
                continue
            instance = self.traverse_spec(value, namespaces)
            if instance:
                self.data.append(instance)

        return self.data

    def django_to_xml(self, instance: "models.DocumentModelMixin") -> etree.ElementTree:
        namespaces = self.mapping.get("_namespaces", {})

        for key, xpath_or_spec in self.mapping.items():
            if key.startswith("_"):
                continue
            if isinstance(xpath_or_spec, dict) and "_model" in xpath_or_spec and isinstance(instance, self._get_model_class(xpath_or_spec)):
                for element in self._get_elements(xpath_or_spec, namespaces):
                    # this are all elements from the original xml
                    mapper = self.__class__(
                        element, xpath_or_spec | {"_namespaces": namespaces})
                    mapper._update_element(instance)

        return self.current_element.getroottree()

    def _update_element(self, obj: Model):
        namespaces = self.mapping.get("_namespaces", {})

        for fieldname, xpath_or_spec in self.mapping.get("fields", {}).items():
            # TODO: are there other fields that need to be ignored?
            if fieldname.startswith("mptt_"):
                continue
            if isinstance(xpath_or_spec, str):
                # simple XPath
                self._set_value(xpath_or_spec, getattr(obj, fieldname))
            elif isinstance(xpath_or_spec, dict) and "_inputs" in xpath_or_spec and "_reverse_parser" in xpath_or_spec:
                reverse_parser_func = load_function(
                    xpath_or_spec["_reverse_parser"])
                values = reverse_parser_func(self, getattr(obj, fieldname))
                if not isinstance(values, (list, tuple)):
                    values = (values,)
                for xpath, value in zip(xpath_or_spec["_inputs"], values):
                    self._set_value(xpath, value)
            elif isinstance(xpath_or_spec, dict) and "_model" in xpath_or_spec:
                # related object fk/m2m/reverse
                logging.warning(
                    f"Processing related field '{fieldname}' of model '{obj._meta.label}'")
                is_many = is_many_relation(obj, fieldname)

                if not is_many:
                    try:
                        related_obj = getattr(obj, fieldname)
                    except ObjectDoesNotExist:
                        # happens if this is a reverse one-to-one relation and no related object exists
                        related_obj = None

                    if related_obj is None:
                        # TODO: should the corresponding xml element be deleted or left untouched?
                        continue

                    xpath = self.compile_concrete_xpath(
                        related_obj, xpath_or_spec)
                    element = self._get_element(xpath, create=True)
                    mapper = self.__class__(
                        element, xpath_or_spec | {"_namespaces": namespaces})

                    mapper._update_element(related_obj)
                elif "_parser" in xpath_or_spec:
                    if "_reverse_parser" not in xpath_or_spec:
                        continue
                    xpath = self.compile_concrete_xpath(obj, xpath_or_spec)
                    old_element = self._get_element(xpath)
                    reverse_parser_func = load_function(
                        xpath_or_spec["_reverse_parser"])
                    new_element = reverse_parser_func(
                        self, getattr(obj, fieldname))
                    old_element.getparent().replace(old_element, new_element)
                else:
                    elements = self._get_elements(xpath_or_spec, namespaces)
                    # obj.fieldname should be a Manager
                    related_objs = getattr(obj, fieldname).all()

                    while len(related_objs) != len(elements):
                        # TODO: create or delete elements as needed
                        if len(related_objs) > len(elements):
                            self._create_element(xpath_or_spec["_base_xpath"])
                        else:  # len(related_objs) < len(elements)
                            if "//" in xpath_or_spec["_base_xpath"]:
                                # we do not support deleting elements in a nested structure yet
                                break
                            to_be_removed = elements.pop()
                            to_be_removed.getparent().remove(to_be_removed)
                        elements = self._get_elements(
                            xpath_or_spec, namespaces)
                        related_objs = getattr(obj, fieldname).all()
                    else:  # if we break out of the loop, the following block is skipped
                        # TODO: ordering might be an issue here
                        for element, related_obj in zip(elements, related_objs):
                            mapper = self.__class__(
                                element, xpath_or_spec | {"_namespaces": namespaces})
                            mapper._update_element(related_obj)

    def _set_value(self, xpath: str, value: str | int | None):
        if xpath.split("/")[-1].startswith("@"):
            # this is an attribute
            self._set_attribute(xpath, value)
        else:
            self._set_text(xpath, value)

    def _set_text(self, xpath: str, value: str | int | None):
        if value is None or value == "":
            self._delete_element(xpath)
            return

        element = self._get_element(xpath, create=True)
        element.text = str(value)

    def _set_attribute(self, xpath: str, value: str | int | None):
        namespaces = self.mapping.get("_namespaces", {})
        nsprefix, _, step = xpath.split("/")[-1].lstrip("@").rpartition(":")
        ns = namespaces.get(nsprefix, "")

        element = self._get_element(xpath)
        if element is None:
            if value is None or value == "":
                return
            else:
                element = self._create_element(xpath)
        value = str(value) if value is not None else ""
        element.set(f"{{{ns}}}{step}", value)

    def _get_element(self, xpath: str, create: bool = False) -> etree.Element | None:

        namespaces = self.mapping.get("_namespaces", {})
        elements = self.current_element.xpath(xpath, namespaces=namespaces)
        if isinstance(elements, list):
            if len(elements) > 1:
                logging.warning(
                    f"Multiple elements found for xpath '{xpath}'. Using the first one.")
                raise  # TODO: meaningful exception
            if not elements and not create:
                return
            element = elements[0] if elements else self._create_element(xpath)
        else:
            element = elements
        if isinstance(element, etree._ElementUnicodeResult):
            element = element.getparent()
        if not isinstance(element, etree.Element):
            raise  # TODO: meaningful exception
        return element

    def _create_element(self, xpath: str) -> etree.Element:
        namespaces = self.mapping.get("_namespaces", {})
        return util.create_xml_node(parse(xpath), self.current_element, {"namespaces": namespaces})

    def _delete_element(self, xpath: str | None = None):
        namespaces = self.mapping.get("_namespaces", {})

        elements = self.current_element.xpath(
            xpath, namespaces=namespaces) if xpath else [self.current_element]
        for element in elements:
            if (parent := element.getparent()) is None:
                continue
            # TODO: remove this warning or change its level
            logging.warning(
                f"Deleting element at path '{xpath}'")
            if isinstance(element, etree._ElementUnicodeResult):
                parent.text = ""
            else:
                parent.remove(element)
