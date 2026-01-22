from pathlib import Path
from typing import IO, Union

from django.core.exceptions import FieldDoesNotExist
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
    ref_rel = next(field for field in model_cls._meta.related_objects if field.get_accessor_name(
    ) == reverse_field_name)
    if ref_rel:
        return ref_rel.field.name
    return None


def is_many_relation(model, fieldname: str) -> bool:
    try:
        field = model._meta.get_field(fieldname)
    except FieldDoesNotExist:
        field = next(field for field in model._meta.related_objects if field.get_accessor_name(
        ) == fieldname)

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
