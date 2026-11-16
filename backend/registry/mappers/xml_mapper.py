import logging
from pathlib import Path
from typing import IO, Union
from uuid import uuid4

from django.apps import apps
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ImproperlyConfigured
from django.db import models as db_models
from django.db.models import ForeignKey, JSONField
from lxml import etree
from registry import models
from registry.mappers.cache import GlobalXmlCache
from registry.mappers.utils import (build_concrete_xpath, create_mapped_row,
                                    ensure_element_for_instance,
                                    ensure_mapped_element,
                                    find_mapped_elements,
                                    get_fk_field_name_from_reverse_relation,
                                    get_mapped_value, is_many_relation,
                                    load_file, load_function,
                                    parse_write_path, remove_element_or_attribute,
                                    remove_mapped_element, resolve_write_qname,
                                    set_mapped_value, set_text_or_attribute,
                                    split_path_steps)


# sentinel for a _parser call that failed on the document's current value -
# only then does the write mapper fall back to comparing the serialized text
_PARSE_FAILED = object()


def is_value_spec(entry):
    """True for a mapping entry which is extracted as plain values.

    A value spec maps nested or repeated elements which have no model and no
    persistence of their own (#981, epic #669): the traversal evaluates its
    _base_xpath and maps the fields of every element it finds into a dict. The
    list of those dicts travels with the parsed instance under
    `_<name>_values` and answers as the same list in mapped_values() - the
    persistence path and the extraction path read one and the same traversal,
    no second pass over the XML.
    """
    return isinstance(entry, dict) and entry.get("_values") is True


# The concrete fields whose column holds a list itself. For those the list which
# a multi-valued xpath answered IS the value; every other concrete field is
# single valued and has to be answered by exactly one value (#990).
MANY_VALUE_FIELDS = (JSONField, ArrayField)


def row_items(value):
    """what the row writers iterate: the given list, the empty answer for
    the values that state nothing, the single value wrapped as one row"""
    if isinstance(value, list):
        return value
    if value in (None, {}, ""):
        return []
    return [value]


class XmlMapper:
    db_instance = None

    def __init__(
        self,
        xml: Union[str, Path, bytes, IO, etree._Element],
        mapping: dict,
        uuid=None,
        warnings=None,
        cache=None,
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
            cache: the cache the parsed instances are collected in; defaults
                to the process-global GlobalXmlCache and takes any object with
                the same call surface, e.g. a LocalXmlCache for a mapping run
                which must leave no global state behind (#981).
        """
        self.mapping = mapping
        # Nested mappers share diagnostics so the importer can report them to its user.
        self.warnings = warnings if warnings is not None else []
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
        self.cache = cache if cache is not None else GlobalXmlCache
        self.data = []
        # what the forward traversal produced per mapping key, filled by
        # xml_to_django() and read by mapped_values()
        self._spec_results = {}
        self._traversed = False

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
                uuid=self.uuid,
                warnings=self.warnings,
                # the shared cache and uuid are how a parent spec finds the
                # instances a sub-mapper parsed - with an injectable cache this
                # hand-off must travel through the constructor
                cache=self.cache,
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
        """Sets the value of one concrete field on the parsed instance.

        The xpath of the config may answer any number of nodes: ISO 19139 allows
        one resolution block per part of a dataset and catalogues repeat titles,
        dates and denominators all over their records. A single valued field can
        not be answered with the list of all matches - the ORM refuses the list
        on save() and the whole record ends up in the import error ledger, which
        is how #990 lost records of the GDI-BW catalogue. So the value the
        document names first is kept, as it always was for a CharField, and the
        dropped ones are named in the warnings of this mapper - which the
        harvesting job logs next to the record it imported.
        """
        parsed_value = self.parse_field(
            xml_element, xpath_or_spec, namespaces)
        if isinstance(parsed_value, list):
            parsed_value = self.single_value_for_field(
                field_name, instance, parsed_value)

        if parsed_value is not None:
            setattr(instance, field_name, parsed_value)

    def single_value_for_field(self, field_name, instance, values):
        """The one value a field is answered with out of all its matches.

        A field whose column holds a list keeps the list. Any other field is
        answered by the first value in document order and says which of the
        matched values were dropped; answering the list would cost the record.
        """
        if isinstance(instance._meta.get_field(field_name), MANY_VALUE_FIELDS):
            return values
        if not values:
            return None

        kept, *dropped = values
        warning = (
            f"Mapped {len(values)} values for the single valued field "
            f"'{field_name}'; kept {kept!r} and dropped {dropped!r}.")
        logging.warning(warning)
        self.warnings.append(warning)
        return kept

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

    def handle_value_fields(self, instance, xml_element, spec, namespaces):
        """Extracts the _values specs of a spec into plain python values.

        Every element the value spec's _base_xpath names becomes one dict, in
        document order; a field which matches several nodes inside one element
        answers a list. The values are kept exactly as the XPath names them -
        only an explicit _parser may transform one. The list is attached to the
        parsed instance under `_<name>_values`, so the mapped representation of
        the whole document carries it without a second traversal (#981).
        """
        for value_name, value_spec in self._get_value_fields(spec).items():
            base_xpath = value_spec.get("_base_xpath", ".")
            fields = value_spec.get("fields", {})
            elements = xml_element.xpath(base_xpath, namespaces=namespaces)
            values = [
                {
                    name: self.parse_field(el, xpath_or_spec, namespaces)
                    for name, xpath_or_spec in fields.items()
                }
                for el in elements
            ]
            setattr(instance, f"_{value_name}_values", values)

    def _get_flat_fields(self, spec):
        model_cls = self._get_model_class(spec)
        fields = spec.get("fields", {})
        return {
            key: value for key, value in fields.items()
            if not is_value_spec(value)
            and key in [field.name for field in model_cls._meta.concrete_fields
                        if not isinstance(field, ForeignKey)]
        }

    def _get_reverse_fields(self, spec):
        model_cls = self._get_model_class(spec)
        fields = spec.get("fields", {})
        return {
            key: value for key, value in fields.items()
            if not is_value_spec(value)
            and key in [rel.get_accessor_name() for rel in model_cls._meta.related_objects]
        }

    def _get_foreign_fields(self, spec):
        model_cls = self._get_model_class(spec)
        fields = spec.get("fields", {})
        return {
            key: value for key, value in fields.items()
            if not is_value_spec(value)
            and key in [field.name for field in model_cls._meta.concrete_fields
                        if isinstance(field, ForeignKey)]
        }

    def _get_m2m_fields(self, spec):
        model_cls = self._get_model_class(spec)
        fields = spec.get("fields", {})
        return {
            key: value for key, value in fields.items()
            if not is_value_spec(value)
            and key in [m2m.name for m2m in model_cls._meta.local_many_to_many]
        }

    def _get_value_fields(self, spec):
        fields = spec.get("fields", {})
        return {
            key: value for key, value in fields.items()
            if is_value_spec(value)
        }

    def _get_elements(self, spec, namespaces):
        base_xpath = spec.get("_base_xpath", ".")
        if not base_xpath:
            return [self.current_element]
        elements = self.current_element.xpath(base_xpath, namespaces=namespaces)
        if not elements:
            # Documents of the wild place the information of a field in an other
            # element than the one the field is mainly mapped from. The fallbacks
            # are tried in order and only used while parsing; the reverse mapping
            # only knows _base_xpath, so it always writes to the main element.
            for fallback_xpath in spec.get("_fallback_xpaths", ()):
                elements = self.current_element.xpath(
                    fallback_xpath, namespaces=namespaces)
                if elements:
                    break
        return elements

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
                self.handle_value_fields(instance, el, spec, namespaces)

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
            self._spec_results[key] = instance
            if instance:
                self.data.append(instance)

        self._traversed = True
        return self.data

    def mapped_values(self):
        """The mapped representation of the document as plain python values.

        Returns a dict keyed by the spec key of the mapping ("dataset",
        "service", ...) answering one dict per parsed instance. A dict holds
        every mapped field: the value a flat field was parsed to, the parsed
        related instances projected field by field, and the list of value
        specs (_values) as extracted. Multiple values stay lists, the order is
        document order and the values are the ones the document carries; a
        single valued field answers the one value the mapper kept for it
        (#990).

        This is the read side of the single forward traversal xml_to_django()
        performs - persistence reads the very same parsed instances - so an
        extraction caller gets its values without a PersistenceHandler, without
        a database write and without any second pass over the XML (#981).
        """
        if not self._traversed:
            self.xml_to_django()
        result = {}
        for key, spec in self.mapping.items():
            if key.startswith("_") or not isinstance(spec, dict):
                continue
            produced = self._spec_results.get(key)
            if not produced:
                continue
            instances = produced if isinstance(produced, list) else [produced]
            result[key] = [
                self._project_mapped_values(instance, spec)
                for instance in instances
            ]
        return result

    def _project_mapped_values(self, instance, spec):
        """The mapped fields of one parsed instance as a plain dict.

        Reads only the python objects the traversal left behind - the field
        values it set and the parsed children it attached as _<name>_parsed or
        _<name>_values - and never the XML again. An instance built by a
        _parser without a fields spec is answered by its concrete fields; the
        primary key is left out because an unsaved instance carries a fresh
        random one of no meaning.
        """
        fields = spec.get("fields")
        if not fields:
            return {
                field.name: getattr(instance, field.name, None)
                for field in instance._meta.concrete_fields
                if field is not instance._meta.pk
                and not isinstance(field, ForeignKey)
            }
        m2m_names = {
            field.name
            for field in type(instance)._meta.local_many_to_many
        }
        values = {}
        for name, xpath_or_spec in fields.items():
            if is_value_spec(xpath_or_spec):
                values[name] = getattr(instance, f"_{name}_values", [])
            elif isinstance(xpath_or_spec, dict) and "_model" in xpath_or_spec:
                if name in m2m_names:
                    parsed = getattr(instance, f"_{name}_parsed", None) or []
                    values[name] = [
                        self._project_mapped_values(child, xpath_or_spec)
                        for child in parsed
                    ]
                else:
                    # a foreign key field carries the parsed related instance
                    # or raises on access when the mapper left it empty - which
                    # for an unsaved instance means: not mapped
                    child = getattr(instance, name, None)
                    values[name] = (
                        self._project_mapped_values(child, xpath_or_spec)
                        if child is not None else None
                    )
            else:
                values[name] = getattr(instance, name, None)
        return values

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
                reverse = xpath_or_spec.get("_reverse", {}) or {}
                # A spec may render an other set of instances than the relation it is
                # parsed from. The name of a zero argument method of db_instance which
                # returns the instances to render. Using it implies a 'many' relation.
                source_name = reverse.get("_source")
                field = getattr(db_instance, field_name, None)
                is_many = True if source_name else is_many_relation(
                    db_instance.__class__, field_name)
                base_xpath = xpath_or_spec.get("_base_xpath", ".")

                try:
                    delete_able_elements = {
                        id(e): e
                        for e in xml_element.xpath(base_xpath, namespaces=nsmap)
                    }
                except etree.XPathEvalError as e:
                    msg = f"Error evaluating base_xpath '{base_xpath}' for field '{field_name}': {e}"
                    logging.error(msg)
                    raise ValueError(msg)
                if is_many:

                    related_instances = getattr(
                        db_instance, source_name)() if source_name else field.all()

                    for related_obj in related_instances:
                        synced = self.sync_xml_with_instance(
                            xml_element,
                            xpath_or_spec,
                            related_obj)

                        delete_able_elements.pop(
                            id(synced), None)

                    for elem in delete_able_elements.values():
                        remove_element_or_attribute(elem, ".", nsmap)

                    # Remove wrapper elements which lost their last meaningfull child
                    # while syncing, because they are not valid xml anymore.
                    for prune_xpath in reverse.get("_prune", []):
                        for orphan in xml_element.xpath(prune_xpath, namespaces=nsmap):
                            parent = orphan.getparent()
                            if parent is not None:
                                parent.remove(orphan)
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

    ############################################
    #    mapped values -> XML (write mapper)   #
    ############################################

    def write_mapped_values(self, values: dict):
        """Write the mapped representation back into the parsed document.

        The inverse of mapped_values() (#1242): takes one dict in exactly the
        shape that method answers - scalars as parsed, relations as nested
        dicts and lists - and writes it into the MD_Metadata element this
        mapper holds, in place. What a field is mapped to is touched as the
        field names it: an existing element gets its text or attribute
        replaced, a missing one is created at the position the element order
        table names, and everything the config does not map keeps its bytes.

        The rules the editor's read-write-read round trip relies on:

        * a field missing from ``values``, a value of None and an empty list
          are all "not written" - removing mapped content is an explicit act
          of a later issue, never a side effect of a partial dict;
        * a value the document already carries is left alone, compared both
          as serialized text and through the spec's ``_parser`` - so writing
          back freshly extracted values does not change the document, not
          even the representation of a date;
        * multi-valued fields pair values with matches by position (the same
          document order mapped_values() read them in); surplus values
          create new rows at the spec's ``_reverse._row``, surplus matches
          are removed - but only while the field carries values at all;
        * a field without a ``_reverse_parser`` where one would be needed is
          named in self.warnings and skipped, never guessed at.
        """
        if values is None:
            raise ValueError("write_mapped_values needs a values dict")
        nsmap = self.mapping.get("_namespaces", {})
        element_order = self.mapping.get("_element_order") or {}
        for key, spec in self.mapping.items():
            if key.startswith("_") or not isinstance(spec, dict) \
                    or "_model" not in spec:
                continue
            self._write_spec_values(spec, values, nsmap, element_order)

    def _write_spec_values(self, spec, values, nsmap, element_order):
        record_model = self._get_model_class(spec)
        for name, field in spec.get("fields", {}).items():
            if name not in values:
                continue
            value = values[name]
            if is_value_spec(field):
                # the _values specs are document evidence with no model field
                # of their own - nothing to write back
                continue
            if isinstance(field, dict) and "_model" in field:
                self._write_related_field(
                    record_model, name, field, value, nsmap, element_order)
            else:
                self._write_flat_field(
                    name, field, value, self.current_element, nsmap,
                    element_order)

    def _write_flat_field(self, name, field_spec, value, base_el, nsmap,
                          element_order):
        """Write one scalar field onto the element its path names.

        The first match is written - the same match mapped_values() answered
        for a single valued field (#990); more matches stay untouched.
        """
        shape = self._flat_field_shape(name, field_spec)
        if shape is None:
            return
        path, parser_path, reverse_path = shape
        if value is None or value == "":
            return
        text = load_function(reverse_path)(self, value) if reverse_path \
            else value
        if text is None:
            return
        text = text if isinstance(text, str) else str(text)

        steps, attr, _is_text = parse_write_path(path)
        attr_tag = resolve_write_qname(attr, nsmap) if attr else None
        targets = find_mapped_elements(base_el, steps, nsmap)
        if targets:
            element = targets[0]
            current = get_mapped_value(element, attr_tag)
            if current != text and not self._keeps_own_representation(
                    parser_path, current, value):
                set_mapped_value(element, attr_tag, text)
            return
        element = ensure_mapped_element(base_el, steps, nsmap, element_order)
        set_mapped_value(element, attr_tag, text)

    def _flat_field_shape(self, name, field_spec):
        """How a flat field is written: its one value path, the parser which
        reads it, the reverse parser which writes it - None, with the reason
        named in the warnings, when the config makes it unwritable."""
        if isinstance(field_spec, str):
            return field_spec, None, None
        inputs = field_spec.get("_inputs")
        parser_path = field_spec.get("_parser")
        reverse_path = field_spec.get("_reverse_parser")
        if not reverse_path:
            self.warnings.append(
                f"'{name}' is not writable: the config names no "
                f"_reverse_parser for it")
            return None
        if not inputs or len(inputs) != 1:
            self.warnings.append(
                f"'{name}' is not writable: its _inputs are not one "
                f"value path")
            return None
        return inputs[0], parser_path, reverse_path

    def _keeps_own_representation(self, parser_path, current, value):
        """Whether the document already carries this very value, in its own
        representation - which is the one worth keeping."""
        if not parser_path or current is None:
            return False
        parsed = self._try_parse(parser_path, current)
        return parsed is not _PARSE_FAILED and parsed == value

    def _write_related_field(self, record_model, name, spec, value, nsmap,
                             element_order):
        """Write one related field - a list of rows (m2m) or one row (FK)."""
        base = spec.get("_base_xpath")
        if not base:
            self.warnings.append(
                f"'{name}' is not writable: the spec names no _base_xpath")
            return
        steps, attr, _is_text = parse_write_path(base)
        attr_tag = resolve_write_qname(attr, nsmap) if attr else None

        if not is_many_relation(record_model, name):
            # the reader loops all base matches and answers the instance
            # parsed from the LAST one; the write goes to the same element
            matches = find_mapped_elements(self.current_element, steps, nsmap)
            if value:
                self._write_row_values(
                    name, spec, value,
                    matches[-1] if matches else ensure_mapped_element(
                        self.current_element, steps, nsmap, element_order),
                    attr_tag, nsmap, element_order)
            return

        items = row_items(value)
        if not items:
            # an empty list is "nothing was given", never "delete everything"
            return
        matches = self._parsed_rows(spec, steps, nsmap)
        row_idx = self._row_step_index(name, spec, steps, nsmap)
        if row_idx is None:
            return
        suffix = [step for step in steps[row_idx:] if step.name != "."]
        last_row = (self._climb_row(matches[-1], steps, row_idx)
                    if matches else None)
        for position, item in enumerate(items):
            leaf, last_row = self._row_at_position(
                matches, position, steps, row_idx, suffix, nsmap,
                element_order, last_row)
            self._write_row_values(name, spec, item, leaf, attr_tag, nsmap,
                                   element_order)
        for surplus in matches[len(items):]:
            remove_mapped_element(
                self._climb_row(surplus, steps, row_idx),
                self.current_element)

    def _row_at_position(self, matches, position, steps, row_idx, suffix,
                         nsmap, element_order, last_row):
        """The row element of one value of the collection, and the last row
        of the document after this write.

        The document's own row when it carries this one; else a fresh row -
        beneath the container the base path names when the collection has no
        row at all, after the last row otherwise, because the rows of one
        collection can live in several blocks.
        """
        if position < len(matches):
            return matches[position], last_row
        if last_row is None:
            container = ensure_mapped_element(
                self.current_element, steps[:row_idx], nsmap, element_order)
            leaf = create_mapped_row(container, suffix, nsmap, element_order)
        else:
            leaf = create_mapped_row(
                None, suffix, nsmap, element_order, after=last_row)
        return leaf, self._climb_row(leaf, suffix, 0)

    def _write_row_values(self, name, spec, item, leaf, attr_tag, nsmap,
                          element_order):
        """Write one row of a related field onto the matched or created leaf.

        A spec with fields writes each field path relative to the row
        element; a spec without fields is one serialized value - the shape of
        reference_systems and categories, whose _reverse_parser answers the
        external text of the row.
        """
        fields = spec.get("fields")
        if not fields:
            self._write_serialized_row(name, spec, item, leaf, attr_tag,
                                       nsmap)
            return

        for field_name, field_spec in fields.items():
            if isinstance(item, db_models.Model):
                field_value = getattr(item, field_name, None)
            else:
                field_value = (item or {}).get(field_name)
            self._write_flat_field(
                f"{name}.{field_name}", field_spec, field_value, leaf, nsmap,
                element_order)

    def _write_serialized_row(self, name, spec, item, leaf, attr_tag, nsmap):
        """Write a row the spec answers as one serialized value.

        The row is an instance first and text second: an empty row never
        reached the editor - mapped_values() answers an unsaved ChoiceModel
        row whose only field is its primary key as an empty dict - so there
        is nothing this write could write, and a document which already
        carries the same value in its own representation stays as it is.
        """
        reverse_path = spec.get("_reverse_parser")
        if not reverse_path:
            self.warnings.append(
                f"'{name}' is not writable: the spec names no "
                f"_reverse_parser for its rows")
            return
        instance = self._row_instance(spec, item)
        if instance is None or self._is_empty_row(instance):
            return
        text = load_function(reverse_path)(self, instance)
        if text is None:
            return
        text = str(text)
        current = get_mapped_value(leaf, attr_tag)
        if current == text:
            return
        parser_path = spec.get("_parser")
        if parser_path and current is not None:
            parsed = self._try_parse(parser_path, current)
            if (parsed is not _PARSE_FAILED
                    and isinstance(parsed, db_models.Model)
                    and self._comparable_instance(parsed)
                    == self._comparable_instance(instance)):
                return
        set_mapped_value(leaf, attr_tag, text)

    def _parsed_rows(self, spec, steps, nsmap):
        """The base elements the reader actually turned into rows.

        The reader runs the spec's _parser over every element the _base_xpath
        names and drops the ones it answers None for - the empty
        gco:CharacterString and gco:nilReason placeholders of #989 and #1074.
        Position pairing on the write side has to skip exactly those
        elements, or the values shift onto the wrong rows.
        """
        matches = find_mapped_elements(self.current_element, steps, nsmap)
        parser_path = spec.get("_parser")
        if not parser_path:
            return matches
        parser = load_function(parser_path)
        rows = []
        for el in matches:
            try:
                if parser(self, el) is not None:
                    rows.append(el)
            except Exception:
                # a row the reader would fail on is no row of its answer
                continue
        return rows

    def _row_instance(self, spec, item):
        """The unsaved model instance a row value is serialized from."""
        if isinstance(item, db_models.Model):
            return item
        if not isinstance(item, dict):
            self.warnings.append(
                f"'{spec.get('_model')}' row value is neither dict nor "
                f"instance: {item!r}")
            return None
        model_cls = self._get_model_class(spec)
        names = {f.name for f in model_cls._meta.concrete_fields}
        try:
            return model_cls(
                **{k: v for k, v in item.items() if k in names})
        # an unbuildable row is reported as a warning, never raised
        except Exception as err:  # noqa: BLE001
            self.warnings.append(
                f"can not build {spec.get('_model')} from {item!r}: {err}")
            return None

    @staticmethod
    def _comparable_instance(instance):
        """Field dict of an unsaved instance, the pk left out of the compare."""
        return {
            field.name: getattr(instance, field.name, None)
            for field in instance._meta.concrete_fields
            if field is not instance._meta.pk
        }

    @staticmethod
    def _is_empty_row(instance):
        """True when the value dict carried nothing for this row at all."""
        if getattr(instance, instance._meta.pk.name, None) is not None:
            return False
        return all(
            getattr(instance, field.name, None) is None
            for field in instance._meta.concrete_fields
            if field is not instance._meta.pk
        )

    def _try_parse(self, parser_path, current):
        """The spec's _parser on the document's current value, or failure."""
        try:
            return load_function(parser_path)(self, current)
        except Exception:
            return _PARSE_FAILED

    def _row_step_index(self, name, spec, steps, nsmap):
        """Where the row element of a collection sits in the base steps."""
        row = (spec.get("_reverse") or {}).get("_row")
        if not row:
            self.warnings.append(
                f"'{name}' is not writable: the collection spec names no "
                f"'_reverse._row'")
            return None
        row_steps = split_path_steps(row)
        if not row_steps or row_steps[-1].name in (".", "*"):
            self.warnings.append(
                f"'{name}': _row '{row}' names no element")
            return None
        row_tag = resolve_write_qname(row_steps[-1].name, nsmap)
        for index in range(len(steps) - 1, -1, -1):
            if steps[index].name not in ("*", ".") and \
                    resolve_write_qname(steps[index].name, nsmap) == row_tag:
                return index
        self.warnings.append(
            f"'{name}': _row '{row}' is not a step of its _base_xpath")
        return None

    @staticmethod
    def _climb_row(leaf, steps, row_idx):
        """The row element a matched leaf belongs to."""
        ancestor = leaf
        for _ in range(len(steps) - 1 - row_idx):
            parent = ancestor.getparent()
            if parent is None:
                return ancestor
            ancestor = parent
        return ancestor
