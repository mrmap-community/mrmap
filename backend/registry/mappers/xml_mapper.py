import logging
from pathlib import Path
from typing import IO, Union
from uuid import uuid4

from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from django.db.models import ForeignKey
from lxml import etree
from registry import models
from registry.mappers.cache import GlobalXmlCache
from registry.mappers.utils import (build_concrete_xpath,
                                    ensure_element_for_instance,
                                    get_fk_field_name_from_reverse_relation,
                                    is_many_relation, load_file, load_function,
                                    remove_element_or_attribute,
                                    set_text_or_attribute)


class XmlMapper:
    db_instance = None

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

    def get_all_keys(self):
        return self.cache.get(self.uuid, [])

    def read_all_from_cache(self):
        all_keys = self.get_all_keys()
        return self.cache.get_many(all_keys)

    def get_all_xpaths(self) -> list[str]:
        """
        Returns all cached XPaths (keys) stored in this mapper instance.

        Each key corresponds to an XPath that was used in store_to_cache.
        """
        all_keys = self.get_all_keys()  # e.g., ['uuid:key1', 'uuid:key2', ...]
        prefix = f"{self.uuid}:"

        # Strip the uuid prefix to get the original XPath keys
        xpaths = [key[len(prefix):]
                  for key in all_keys if key.startswith(prefix)]
        return xpaths

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
                elif instance is not None:
                    if is_many:
                        instances.append(instance)
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

    ####################################
    #       Django -> XML stuff        #
    ####################################

    def django_to_xml(self, db_instance: "models.DocumentModelMixin") -> etree.ElementTree:
        # The original capabilitites file for example shall stored in self.xml_root

        # This will parse the original xml and feed the cache with original parsed information.
        # Thats the savest way to get all original deterministic xpaths.
        # self.xml_to_django()

        # all deterministic xpaths are available under self.get_all_xpaths()
        # parsed instances are available under self.read_from_cache()
        # or read all instances by using self.read_all_from_cache()
        self.db_instance = db_instance
        for key, xpath_or_spec in self.mapping.items():
            if key.startswith("_"):
                continue

            if isinstance(xpath_or_spec, dict) and "_model" in xpath_or_spec and isinstance(db_instance, self._get_model_class(xpath_or_spec)):
                # currenct instance matches the current spec branch
                self.sync_spec_to_xml(
                    self.current_element,
                    xpath_or_spec,
                    db_instance
                )

        return self.xml_root.getroottree()

    def sync_xml_with_instance(self, xml_element, xpath_or_spec, instance):
        nsmap = self.mapping.get("_namespaces", {})
        base_xpath = xpath_or_spec.get("_base_xpath", ".")
        from registry.models import FeatureType
        if isinstance(instance, FeatureType):
            i = 0
        concrete_xpath = build_concrete_xpath(
            self,
            xpath_or_spec,
            instance,
        )
        try:
            child_xml_element = xml_element.xpath(
                concrete_xpath,
                namespaces=nsmap
            )
        except etree.XPathEvalError:
            raise RuntimeError(
                f"Invalid expression compiled for model {instance.__class__.__name__}: {concrete_xpath}")

        match(len(child_xml_element)):
            case 1:
                child_xml_element = child_xml_element[0]
            case 0:
                child_xml_element = None
            case _:
                logging.warning(
                    f"multiple elements found with xpath: {base_xpath}")
                # TODO: should we simply remove all xml_elements first and then simply create it from db?
                child_xml_element = child_xml_element[0]
        if not instance and not child_xml_element:
            # nothing to do. xml has no element and db has no instance. thats fine.
            pass

        elif child_xml_element is None and instance:
            # there is no xml element but a db instance. Create this one on XML
            child_xml_element = ensure_element_for_instance(
                self,
                xml_element,
                xpath_or_spec,
                instance,
                nsmap
            )
            self.sync_spec_to_xml(
                child_xml_element,
                xpath_or_spec,
                instance
            )
        elif child_xml_element is not None and instance:
            # existing element found. Sync it with db data.
            self.sync_spec_to_xml(
                child_xml_element,
                xpath_or_spec,
                instance
            )
        return child_xml_element

    def sync_spec_to_xml(self, xml_element: etree._Element, spec, db_instance):
        if not isinstance(xml_element, etree._Element):
            raise ValueError(
                f"can not sync for element of type {type(xml_element)}")

        if isinstance(spec, dict) and "_reverse_parser" in spec:
            # Use _reverse_parser if defined
            reverse_parser_path = spec.get(
                "_reverse_parser") if isinstance(spec, dict) else None
            if reverse_parser_path:
                parser_func = load_function(reverse_parser_path)
                # parser function shall creates / update / delete the xml node
                parser_func(self, xml_element, db_instance)
            return

        ignore_fields = spec.get("_reverse", {}).get(
            "_ignore_fields", []) if isinstance(spec, dict) else []

        for field_name, xpath_or_spec in spec.get("fields", {}).items():
            if field_name in ignore_fields:
                continue
            if isinstance(xpath_or_spec, str) or isinstance(xpath_or_spec, dict) and "_model" not in xpath_or_spec:
                # simple concrete field
                self.sync_field_to_xml(
                    xml_element,
                    field_name,
                    xpath_or_spec,
                    db_instance
                )
            elif isinstance(xpath_or_spec, dict) and "_model" in xpath_or_spec:
                # related model
                nsmap = self.mapping.get("_namespaces", {})
                field = getattr(db_instance, field_name, None)
                is_many = is_many_relation(db_instance.__class__, field_name)
                base_xpath = xpath_or_spec.get("_base_xpath", ".")

                try:
                    delete_able_elements = {
                        e.getroottree().getpath(e): e
                        for e in xml_element.xpath(base_xpath, namespaces=nsmap)
                    }
                except etree.XPathEvalError as e:
                    msg = f"Error evaluating base_xpath '{base_xpath}' for field '{field_name}': {e}"
                    logging.error(msg)
                    raise ValueError(msg)
                if is_many:

                    for related_obj in field.all():
                        synced = self.sync_xml_with_instance(
                            xml_element,
                            xpath_or_spec,
                            related_obj)

                        delete_able_elements.pop(
                            synced.getroottree().getpath(synced), None)

                    for elem in delete_able_elements.values():
                        remove_element_or_attribute(elem, ".", nsmap)
                else:
                    if not field:
                        # happens if a one to one kind relation is None.
                        # TODO: find all child elements based on xpath and remove them
                        # xpath = xpath_or_spec.get("fields", {}).get(field_name)
                        # remove_element_or_attribute(
                        #    xml_element,
                        #    xpath,
                        #    nsmap
                        # )
                        continue
                    self.sync_xml_with_instance(
                        xml_element,
                        xpath_or_spec,
                        field)

    def sync_field_to_xml(self, xml_element, field_name, xpath_or_spec, instance):
        value = getattr(instance, field_name, None)

        # Use _reverse_parser if defined
        reverse_parser_path = xpath_or_spec.get(
            "_reverse_parser") if isinstance(xpath_or_spec, dict) else None
        if reverse_parser_path:
            parser_func = load_function(reverse_parser_path)
            # parser function shall creates / update / delete the xml node
            parser_func(self, value)
        elif isinstance(xpath_or_spec, str):
            self.set_xml_value(xml_element, xpath_or_spec, value)

    def set_xml_value(self, xml_element, xpath: str, value):
        """
        Sets a value in an XML element based on XPath or spec.
        Supports element text or attributes (e.g., ./@attr or ./@prefix:attr)
        """
        namespaces = self.mapping.get("_namespaces", {})
        if not value:
            pass
            # remove_element_or_attribute(xml_element, xpath, namespaces)
        else:
            # set value normally
            set_text_or_attribute(xml_element, xpath, namespaces, value)
