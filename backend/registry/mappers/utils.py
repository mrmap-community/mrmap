from pathlib import Path
from typing import IO, Union

from django.apps import apps
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models import ManyToManyField
from django.db.models.fields.related import ForeignObjectRel
from lxml import etree


def load_function(path: str):
    """Importiert eine Funktion aus einem string 'module.func'"""
    mod_name, func_name = path.rsplit(".", 1)
    mod = __import__(mod_name, fromlist=[func_name])
    return getattr(mod, func_name)


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


def get_fk_field_name_from_reverse_relation(model_cls, reverse_field_name):
    """
    Gegeben: Parent-Modellklasse und Reverse-Relation-Feldname (z.B. 'layers').
    Liefert: FK-Feldname im Child-Modell, das auf Parent verweist (z.B. 'service').
    """
    try:
        ref_rel = next(field for field in model_cls._meta.related_objects if field.get_accessor_name(
        ) == reverse_field_name)
    except StopIteration:
        ref_rel = None
    if ref_rel:
        return ref_rel.field.name
    return None


def is_many_relation(model, fieldname: str) -> bool:
    try:
        field = model._meta.get_field(fieldname)
    except FieldDoesNotExist:
        try:
            field = next(field for field in model._meta.related_objects if field.get_accessor_name(
            ) == fieldname)
        except StopIteration:
            field = None

    match field:
        case ManyToManyField():
            return True
        case ForeignObjectRel() if field.multiple:
            return True
        case _:
            return False


def xpath_literal(value: str) -> str:
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    parts = value.split("'")
    return "concat(" + ", \"'\", ".join(f"'{p}'" for p in parts) + ")"


def normalize_predicate_xpath(relative_xpath: str) -> str | None:
    """
    Convert a relative xpath (./wms:Name, ./@queryable)
    into a predicate-safe xpath (wms:Name, @queryable).
    """
    if not isinstance(relative_xpath, str):
        return None

    if relative_xpath.startswith("./"):
        return relative_xpath[2:]

    if relative_xpath.startswith("@"):
        return relative_xpath

    return None


def normalize_base_xpath_for_child(base_xpath: str) -> str:
    """
    Convert a base xpath into a relative xpath suitable for appending
    to a resolved parent xpath.
    """

    # Relative already
    if base_xpath.startswith("./"):
        return base_xpath[2:]

    # Absolute or descendant search — take last step only
    parts = [p for p in base_xpath.split("/") if p and p != "."]
    return parts[-1]


def is_editable_concrete_field(instance, field_name) -> bool:
    try:
        field = instance._meta.get_field(field_name)
    except FieldDoesNotExist:
        return False

    if not field.editable:
        return False

    if field.many_to_many or field.one_to_many:
        return False

    return True


def compose_xpath(parent_xpath: str, child_base_xpath: str) -> str:
    child = normalize_base_xpath_for_child(child_base_xpath)
    return f"{parent_xpath}/{child}"


def elements_equal(a: etree.Element, b: etree.Element) -> bool:
    return (
        a.tag == b.tag
        and (a.text or "").strip() == (b.text or "").strip()
        and a.attrib == b.attrib
        and len(a) == len(b)
        and all(elements_equal(c1, c2) for c1, c2 in zip(a, b))
    )


def get_unique_fields(model_cls: models.Model):
    """Gibt die Unique-Feld-Kombinationen für das Modell zurück."""
    unique_sets = []

    for field in model_cls._meta.concrete_fields:
        if field.unique:
            unique_sets.append((field.name,))

    for constraint in getattr(model_cls._meta, "constraints", []):
        if isinstance(constraint, models.UniqueConstraint):
            unique_sets.append(tuple(constraint.fields))

    return unique_sets


def find_spec_for_instance(spec: dict, instance):
    """Sucht rekursiv das Spec für eine Instanz."""
    for key, value in spec.items():
        if not isinstance(value, dict):
            continue
        model_label = value.get("_model")
        if model_label:
            model_cls = apps.get_model(model_label)
            if isinstance(instance, model_cls):
                return value
        # rekursiv
        for field_spec in value.get("fields", {}).values():
            if isinstance(field_spec, dict) and "_model" in field_spec:
                found = find_spec_for_instance(
                    {key: field_spec}, instance)
                if found:
                    return found
    return {}


def ensure_path(root, xpath, nsmap=None):
    """
    Ensure that the given XPath exists under root.
    Returns the element or text target.

    Handles simple XPaths and ending with /text().
    """
    parts = xpath.strip("/").split("/")
    current = root
    is_text = False

    # Check if last part is text()
    if parts[-1] == "text()":
        is_text = True
        parts = parts[:-1]

    for part in parts:
        tag_name = part.split("[")[0]  # ignore any predicate
        found = current.find(tag_name, namespaces=nsmap)
        if found is None:
            if ":" in tag_name:
                prefix, local = tag_name.split(":", 1)
                ns_uri = nsmap[prefix]
                tag = f"{{{ns_uri}}}{local}"
            else:
                tag = tag_name
            found = etree.SubElement(current, tag)
        current = found

    return current, is_text


def remove_empty_parents(element, stop_at):
    """
    Recursively remove element if it has no text, no attributes,
    and no child elements. Stop at the stop_at element.
    """
    while element is not None and element != stop_at:
        if element.text and element.text.strip():
            break
        if element.attrib:
            break
        if list(element):
            break
        parent = element.getparent() if hasattr(element, 'getparent') else None
        if parent is not None:
            parent.remove(element)
        element = parent


def remove_element_or_attribute(xml_element, xpath: str, nsmap: dict):
    # Remove element or attribute
    if xpath.startswith("@") or "/@" in xpath:
        parent_path, attr_name = xpath.rsplit(
            "/@", 1) if "/@" in xpath else (".", xpath[1:])
        if ":" in attr_name:
            prefix, local_name = attr_name.split(":", 1)
            ns_uri = nsmap.get(prefix)
            if not ns_uri:
                raise ValueError(
                    f"Namespace prefix '{prefix}' not found in mapping")
            attr_name = f"{{{ns_uri}}}{local_name}"

        leaf, _ = ensure_path(xml_element, parent_path, nsmap)
        if attr_name in leaf.attrib:
            del leaf.attrib[attr_name]
        remove_empty_parents(leaf, xml_element)
    else:
        leaf, _ = ensure_path(xml_element, xpath, nsmap)
        parent = leaf.getparent() if hasattr(leaf, 'getparent') else None
        if parent is not None:
            parent.remove(leaf)
        else:
            # if no parent, just clear the text
            leaf.text = None
    return  # early exit after removal


def set_text_or_attribute(xml_element, xpath: str, nsmap: dict, value):
    if xpath.startswith("@") or "/@" in xpath:
        # Attribute
        parent_path, attr_name = xpath.rsplit(
            "/@", 1) if "/@" in xpath else (".", xpath[1:])
        if ":" in attr_name:
            prefix, local_name = attr_name.split(":", 1)
            ns_uri = nsmap.get(prefix)
            if not ns_uri:
                raise ValueError(
                    f"Namespace prefix '{prefix}' not found in mapping")
            attr_name = f"{{{ns_uri}}}{local_name}"

        leaf, _ = ensure_path(xml_element, parent_path, nsmap)
        leaf.set(attr_name, str(value))

    else:
        leaf, _ = ensure_path(xml_element, xpath, nsmap)
        leaf.text = str(value)


def build_concrete_xpath(spec: dict, instance) -> str:
    """
    Build a concrete XPath from a Django model instance using its spec mapping.
    Works recursively with nested models.

    Args:
        spec: Mapping dictionary for the model (must contain _base_xpath and optionally _identifier)
        instance: Django model instance

    Returns:
        str: Concrete XPath pointing to this instance
    """
    base_xpath = spec.get("_base_xpath", "").rstrip("/")
    identifier_cfg = spec.get("_identifier")

    # 1️⃣ Build identifier XPath from template
    identifier_xpath = ""
    if identifier_cfg:
        if isinstance(identifier_cfg, str):
            template = identifier_cfg
        elif isinstance(identifier_cfg, dict) and "xpath" in identifier_cfg:
            template = identifier_cfg["xpath"]
        else:
            raise ValueError(
                "_identifier must be string or dict with 'xpath' key")

        # Use instance fields to fill template
        fields = {attr: getattr(instance, attr, None)
                  for attr in instance.__dict__}
        try:
            identifier_xpath = template.format(**fields)
        except KeyError as e:
            raise KeyError(f"Instance missing field for xpath template: {e}")

    # 2️⃣ Handle relative XPaths like "." or "./field"
    if identifier_xpath.startswith("./"):
        identifier_xpath = identifier_xpath[2:]
    elif identifier_xpath == ".":
        identifier_xpath = ""

    # 3️⃣ Join base_xpath and identifier
    parts = [base_xpath]
    if identifier_xpath:
        parts.append(identifier_xpath)

    concrete_xpath = "/".join(part for part in parts if part)
    return concrete_xpath


def ensure_element_for_instance(
    parent: etree._Element,
    spec: dict,
    instance,
    nsmap: dict
) -> etree._Element:
    """
    Ensure that the XML element for a Django instance exists
    and return it.
    """
    concrete_xpath = build_concrete_xpath(spec, instance)

    element = parent.xpath(concrete_xpath, namespaces=nsmap)
    if element:
        return element[0]

    # Create path step by step
    leaf, _ = ensure_path(parent, concrete_xpath, nsmap)
    return leaf
