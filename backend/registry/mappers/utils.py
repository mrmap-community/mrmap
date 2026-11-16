import re
from datetime import datetime
from pathlib import Path
from typing import IO
from xml.sax.saxutils import escape as xml_escape

from django.apps import apps
from django.contrib.postgres.fields import DateTimeRangeField
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models import ManyToManyField
from django.db.models.fields.related import ForeignObjectRel
from django.utils.timezone import get_default_timezone, is_naive, make_aware
from lxml import etree
from psycopg.types.range import Range


def load_function(path: str):
    """Importiert eine Funktion aus einem string 'module.func'"""
    mod_name, func_name = path.rsplit(".", 1)
    mod = __import__(mod_name, fromlist=[func_name])
    return getattr(mod, func_name)


def load_file(xml: str | Path | bytes | IO) -> bytes:
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
        # Nullable unique fields (such as update_candidate_of) may be NULL on
        # multiple rows, so they cannot reliably identify a parsed instance.
        if field.unique and not field.null:
            unique_sets.append((field.name,))

    for constraint in getattr(model_cls._meta, "constraints", []):
        if isinstance(constraint, models.UniqueConstraint):
            unique_sets.append(tuple(constraint.fields))

    return unique_sets


def find_spec_for_instance(spec: dict, instance):
    """Sucht rekursiv das Spec für eine Instanz."""
    for key, value in spec.items():
        if _spec_matches_instance(value, instance):
            return value
        # rekursiv
        for field_spec in _model_field_specs(value):
            found = find_spec_for_instance(
                {key: field_spec}, instance)
            if found:
                return found
    return {}


def _spec_matches_instance(value, instance):
    """True when the spec names the model the instance is one of."""
    if not isinstance(value, dict):
        return False
    model_label = value.get("_model")
    if not model_label:
        return False
    return isinstance(instance, apps.get_model(model_label))


def _model_field_specs(value):
    """The nested field specs of a spec which carries a model."""
    if not isinstance(value, dict):
        return ()
    return (fs for fs in value.get("fields", {}).values()
            if isinstance(fs, dict) and "_model" in fs)


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
        _remove_attribute(xml_element, xpath, nsmap)
    else:
        _remove_element(xml_element, xpath, nsmap)


def _remove_attribute(xml_element, xpath: str, nsmap: dict):
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


def _remove_element(xml_element, xpath: str, nsmap: dict):
    leaf, _ = ensure_path(xml_element, xpath, nsmap)
    parent = leaf.getparent() if hasattr(leaf, 'getparent') else None
    if parent is not None:
        parent.remove(leaf)
    else:
        # if no parent, just clear the text
        leaf.text = None


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


def resolve_field(obj, path: str):
    """
    Resolve a dotted path like 'operation.label' from an object.
    If the final attribute is callable, call it automatically.
    """
    current = obj
    parts = path.split(".")
    for i, attr in enumerate(parts):
        if current is None:
            return None
        current = getattr(current, attr, None)
    # If the final value is callable, call it
    if callable(current):
        return current()
    return current


def build_concrete_xpath(mapper, spec: dict, instance: "models.Model") -> str:
    """
    Build a concrete XPath from a Django model instance using its spec mapping.
    Supports nested attributes and automatically calls callables.

    Args:
        spec: Mapping dictionary for the model (must contain _base_xpath and optionally _identifier)
        instance: Django model instance

    Returns:
        str: Concrete XPath pointing to this instance
    """
    identifier_cfg = spec.get("_reverse", {}).get("_identifier")

    if not identifier_cfg:
        # Fallback to _base_xpath if no identifier was found
        return spec.get("_base_xpath", ".")

    # 🔹 CASE 1: compiler function (preferred)
    if "compiler" in identifier_cfg:
        return _identifier_via_compiler(identifier_cfg, mapper, instance)

    # 🔹 CASE 2: literal / template XPath
    if "xpath" not in identifier_cfg:
        raise ValueError(
            "_identifier must define either 'compiler' or 'xpath'"
        )

    # Normalize relative paths
    identifier_xpath = _identifier_via_template(identifier_cfg, instance)
    if identifier_xpath:
        return identifier_xpath

    # Fallback to _base_xpath if no identifier was found
    base_xpath = spec.get("_base_xpath", ".")

    return base_xpath


def _identifier_via_compiler(identifier_cfg, mapper, instance):
    try:
        func = load_function(identifier_cfg["compiler"])
        return func(mapper, instance)
    except Exception as e:
        raise RuntimeError(
            f"Error generating xpath via compiler "
            f"'{identifier_cfg['compiler']}': {e}"
        )


def _identifier_via_template(identifier_cfg, instance):
    xpath_spec = identifier_cfg["xpath"]

    if not isinstance(xpath_spec, str):
        raise ValueError("_identifier['xpath'] must be a string")

    field_names = set(re.findall(r"{([\w\.]+)}", xpath_spec))
    field_values = {}

    for name in field_names:
        value = resolve_field(instance, name)
        if value is None:
            raise KeyError(
                f"Instance missing field for xpath template '{identifier_cfg}': {name}")
        field_values[name] = xml_escape(str(value))

    return xpath_spec.format(**field_values)


def split_parent_and_leaf(xpath: str):
    s = xpath.strip("/")
    if not s:
        raise ValueError("Invalid XPath")

    parts = _split_path_parts(s)

    if not parts:
        raise ValueError("Invalid XPath")

    parent_parts = parts[:-1]
    leaf_part = parts[-1]

    return parent_parts, leaf_part


def _split_path_parts(s: str):
    """The path parts, split on the slashes outside quotes and predicates."""
    parts = []
    buf = []
    bracket_depth = 0
    in_single = False
    in_double = False

    for ch in s:
        # split on slashes only at top level (not inside predicates)
        if (ch == "/" and not in_single and not in_double
                and bracket_depth == 0):
            parts.append("".join(buf))
            buf = []
            continue

        in_single, in_double, bracket_depth = _advance_path_state(
            ch, in_single, in_double, bracket_depth)
        buf.append(ch)

    if buf:
        parts.append("".join(buf))

    return parts


def _advance_path_state(ch, in_single, in_double, bracket_depth):
    """The scanner state after reading one more character.

    Quote states toggle (ignored when inside the other quote type) and
    predicate depth is tracked only when not inside quotes.
    """
    if ch == "'" and not in_double:
        return not in_single, in_double, bracket_depth
    if ch == '"' and not in_single:
        return in_single, not in_double, bracket_depth
    if in_single or in_double:
        return in_single, in_double, bracket_depth
    if ch == "[":
        bracket_depth += 1
    elif ch == "]":
        bracket_depth = max(0, bracket_depth - 1)
    return in_single, in_double, bracket_depth


def extract_tag_name(xpath_part: str) -> str:
    # Removes predicates like [text()='foo']
    return xpath_part.split("[", 1)[0]


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


def ensure_element_for_instance(
    mapper,
    parent: etree._Element,
    spec: dict,
    instance,
    nsmap: dict,
) -> etree._Element:
    """
    Ensure that the XML element for a Django instance exists
    and return it.
    """
    xpath_for_creation = build_concrete_xpath(mapper, spec, instance)

    parent_parts, leaf_part = split_parent_and_leaf(xpath_for_creation)
    leaf_tag = extract_tag_name(leaf_part)

    # Ensure the parent path exists
    parent_xpath = "/".join(parent_parts)
    parent_elem, _ = ensure_path(parent, parent_xpath, nsmap)

    # Resolve namespace-aware tag
    if ":" in leaf_tag:
        prefix, local = leaf_tag.split(":", 1)
        ns_uri = nsmap[prefix]
        tag = f"{{{ns_uri}}}{local}"
    else:
        tag = leaf_tag

    # ALWAYS create a new leaf element

    return etree.SubElement(parent_elem, tag)


def normalize_key_value(field, value):
    if value is None:
        return None

    # LIST → tuple
    if isinstance(value, list):
        return tuple(normalize_key_value(field, v) for v in value)

    # DICT → sorted tuple
    if isinstance(value, dict):
        return tuple(
            sorted((k, normalize_key_value(field, v))
                   for k, v in value.items())
        )

    # SET → sorted tuple
    if isinstance(value, set):
        return tuple(sorted(value))

    # DateTimeRangeField
    if isinstance(field, DateTimeRangeField):
        return _normalize_range(value)

    # datetime
    if isinstance(value, datetime):
        return _normalize_datetime(value)

    return value


def _normalize_range(value):
    """The range of a DateTimeRangeField as its comparable tuple."""
    if not isinstance(value, Range):
        return value

    return (
        _normalize_datetime(value.lower),
        _normalize_datetime(value.upper),
        value.bounds,
    )


def _normalize_datetime(dt):
    if dt is None:
        return None
    if is_naive(dt):
        dt = make_aware(dt, get_default_timezone())
    return dt.astimezone(get_default_timezone())


def get_key_fields(model_cls):
    unique_sets = get_unique_fields(model_cls)
    key_fields = None
    for fields in unique_sets:
        if fields != ('id',):
            key_fields = fields
            break

    # fallback, falls kein anderes eindeutiges Feld existiert
    if key_fields is None:
        key_fields = ('id',)
    return key_fields


def make_instance_key(instance, key_fields=None):
    model = type(instance)
    if not key_fields:
        key_fields = get_key_fields(model)
    return tuple(
        normalize_key_value(
            model._meta.get_field(f),
            getattr(instance, f)
        )
        for f in key_fields
    )


def sort_key_for_instance(instance, key_fields=None):
    """Comparable form of the instance key, to order instances by their key.

    Concurrent imports write the shared lookup tables (Keyword, ReferenceSystem,
    MetadataContact, ...) and have to insert the same rows in the same order in
    every transaction: inserting them in the order a document happens to carry
    them lets two transactions wait for each other's entry in the same unique
    index in opposite order, which Postgres resolves by aborting one of them
    with a deadlock (#817).

    Key values are nullable and of mixed types, so they are compared by their
    presence and text representation instead of their own ordering, which keeps
    None and a foreign key instance comparable with the other values.
    """
    return tuple(
        (value is not None, _comparable_value(value))
        for value in make_instance_key(instance, key_fields)
    )


def _comparable_value(value):
    if isinstance(value, models.Model):
        # a foreign key can be part of a unique key, see OperationUrl
        return f"{value._meta.label}:{value.pk}"
    return str(value)


# ---------------------------------------------------------------------------
# write path (issue #1242)
#
# The primitives below let the mapper write a mapped value back into the
# document it was read from. They know exactly the step forms the record
# configs use: relative child steps, `*` and `*[self::A or self::B]` unions,
# `[@attr]`/`[@attr='v']` predicates, relative-path conditions like the
# otherRestrictions one of access_constraints, a final `@attr` or `text()`
# step, and the self step `.`. Anything else is refused loudly rather than
# guessed at - a half-read predicate could write a value into the wrong
# element, which is the exact failure the atomic activation of #1244 must
# never see.
# ---------------------------------------------------------------------------

_ATTR_EQ_RE = re.compile(r'^@([\w.:-]+)\s*=\s*(["\'])(.*?)\2$')
_ATTR_RE = re.compile(r'^@([\w.:-]+)$')
_SELF_RE = re.compile(r'^self::([\w.:-]+)')


class _PathStep:
    """One child step of a mapped relative path.

    `name` is the prefixed element name ("gmd:title"), "*" for a wildcard or
    None for the self step; `predicate` is the predicate text without the
    square brackets or None.
    """

    __slots__ = ("raw", "name", "predicate")

    def __init__(self, raw):
        self.raw = raw
        bracket = raw.find("[")
        if bracket == -1:
            self.name = raw
            self.predicate = None
        else:
            self.name = raw[:bracket]
            self.predicate = raw[bracket + 1:-1]

    def __repr__(self):
        return f"<PathStep {self.raw}>"


def resolve_write_qname(name, nsmap):
    """The lxml tag for a prefixed config name; None for '*'."""
    if name == "*":
        return None
    if ":" in name:
        prefix, local = name.split(":", 1)
        uri = nsmap.get(prefix)
        if not uri:
            raise ValueError(
                f"Namespace prefix '{prefix}' not found in mapping")
        return f"{{{uri}}}{local}"
    return name


def _step_tag(step, nsmap):
    """The tag a step names; for a self:: union the first of the alternatives."""
    if step.predicate and _SELF_RE.match(step.predicate.strip()):
        return resolve_write_qname(_SELF_RE.match(step.predicate.strip()).group(1), nsmap)
    return resolve_write_qname(step.name, nsmap)


def split_path_steps(xpath):
    """Split a relative mapped path into its child steps.

    A leading "./" is dropped; "." answers the single self step. Splits on
    top-level "/" only - quoted predicates with slashes inside stay intact.
    """
    path = xpath.strip()
    while path.startswith("./"):
        path = path[2:]
    if not path or path == ".":
        return [_PathStep(".")]
    parts, leaf = split_parent_and_leaf(path)
    if not parts:
        return [_PathStep(leaf)]
    return split_path_steps("/".join(parts)) + [_PathStep(leaf)]


def parse_write_path(xpath):
    """(element steps, attribute, is_text) of a mapped value path.

    A final "@attr" or "text()" step is answered apart; the element steps
    always name the element the value is written on.
    """
    path = xpath.strip()
    while path.startswith("./"):
        path = path[2:]
    attr = None
    is_text = False
    if path.startswith("@"):
        return [], path[1:], False
    if path.endswith("/text()") or path == "text()":
        path = path[: -len("text()")].rstrip("/")
        is_text = True
        if not path:
            return [], None, True
    steps = split_path_steps(path)
    if steps and steps[-1].name.startswith("@"):
        attr = steps[-1].name[1:]
        steps = steps[:-1]
    return steps, attr, is_text


def _step_qname_or_none(step, nsmap):
    return resolve_write_qname(step.name, nsmap) if step.name not in ("*", ".") else None


def _predicate_holds(el, predicate, nsmap):
    """Evaluate a step predicate against one candidate element."""
    try:
        return bool(el.xpath(f"self::*[{predicate}]", namespaces=nsmap))
    except etree.XPathEvalError as err:
        raise ValueError(
            f"Unsupported predicate '[{predicate}]' for writing: {err}")


def _children_named(el, tag, predicate, nsmap):
    """The children one element offers to a step: real elements, of the tag
    the step names, and only those the predicate holds for."""
    for child in el:
        if not isinstance(child.tag, str):
            continue
        if tag is not None and child.tag != tag:
            continue
        if predicate and not _predicate_holds(child, predicate, nsmap):
            continue
        yield child


def find_mapped_elements(base_el, steps, nsmap):
    """The elements the child steps name below base_el, in document order."""
    current = [base_el]
    for step in steps:
        if step.name == ".":
            continue
        tag = _step_qname_or_none(step, nsmap)
        nxt = [child for el in current
               for child in _children_named(
                   el, tag, step.predicate, nsmap)]
        if not nxt:
            return []
        current = nxt
    return current


def _seed_predicate(child, step, nsmap):
    """Recreate what a predicate demands of a freshly created element.

    `@attr='v'` sets the attribute, a `self::` union already picked its first
    alternative at creation, and a relative-path condition like the
    otherRestrictions one is seeded beneath the new element - attribute value
    and element text of its deepest node included, which is how catalogue
    records write a codelist element. Predicates of any other shape raise.
    """
    predicate = (step.predicate or "").strip()
    if not predicate:
        return
    if _SELF_RE.match(predicate):
        # the union picked its first alternative at creation
        return
    for condition in re.split(r"(?<=\s)and(?=\s)", predicate):
        condition = condition.strip()
        eq = _ATTR_EQ_RE.match(condition)
        if eq:
            child.set(resolve_write_qname(eq.group(1), nsmap), eq.group(3))
            continue
        if _ATTR_RE.match(condition):
            # a bare existence predicate names no value to set
            raise ValueError(
                f"can not create {step.raw}: predicate demands an attribute "
                f"without naming its value")
        _seed_chain_condition(child, condition, step, nsmap)


def _seed_chain_condition(child, condition, step, nsmap):
    """Seed the relative-path condition of a predicate below the new element.

    `gmd:accessConstraints/gmd:MD_RestrictionCode/@codeListValue="other-"`
    pins an attribute deep below the created element; the chain is created,
    the attribute set, and the element text mirrors the value the way
    catalogue records write a codelist element. A condition without a pinned
    value cannot be satisfied without inventing one, so it raises.
    """
    segments = condition.split("/")
    attr = value = None
    if segments[-1].startswith("@"):
        eq = _ATTR_EQ_RE.match(segments[-1])
        if not eq:
            raise ValueError(
                f"can not create {step.raw}: existence-only condition "
                f"'{condition}' names no value to seed")
        attr, value = eq.group(1), eq.group(3)
        segments = segments[:-1]
    elif any(seg.startswith("@") for seg in segments):
        raise ValueError(
            f"can not create {step.raw}: unsupported predicate shape")
    if not segments:
        raise ValueError(
            f"can not create {step.raw}: unsupported predicate")
    el = child
    for segment in segments:
        path_step = _PathStep(segment)
        tag = _step_tag(path_step, nsmap)
        if tag is None:
            raise ValueError(
                f"can not create wildcard step '{segment}' for predicate "
                f"seeding")
        found = el.find(tag)
        if found is None:
            found = _new_child(el, segment, tag)
        el = found
    if attr is None:
        raise ValueError(
            f"can not create {step.raw}: condition '{condition}' pins no "
            f"value to seed")
    el.set(resolve_write_qname(attr, nsmap), value)
    if el.text is None:
        el.text = value


def _new_child(parent, _raw_name, tag, element_order=None):
    """Create *tag* below *parent* at the position the schema order names."""
    el = etree.SubElement(parent, tag)
    if element_order:
        _place_ordered(parent, el, element_order)
    # keep the pretty-print shape: inherit the indentation of a neighbour
    prev = el.getprevious()
    el.tail = prev.tail if prev is not None else parent.text
    return el


def _place_ordered(parent, el, element_order):
    """Move the freshly appended *el* before the first known-later child."""
    try:
        parent_local = etree.QName(parent).localname
    except ValueError:  # pragma: no cover - not an element
        return el
    order = element_order.get(parent_local)
    if not order:
        return el
    try:
        index = order.index(etree.QName(el).localname)
    except ValueError:
        return el
    for child in parent:
        if child is el or not isinstance(child.tag, str):
            continue
        try:
            child_local = etree.QName(child).localname
        except ValueError:  # pragma: no cover - processing instruction
            continue
        if child_local in order and order.index(child_local) > index:
            child.addprevious(el)
            return el
    return el


def ensure_mapped_element(base_el, steps, nsmap, element_order=None):
    """The element the steps name below base_el, creating what is missing.

    Missing steps are created at the schema position (see the element order
    table in configs/iso_access.py) and seeded from their predicates. A step
    that must be created but cannot - a wildcard, an unparseable predicate -
    raises instead of writing somewhere else.
    """
    current = base_el
    for step in steps:
        if step.name == ".":
            continue
        matches = find_mapped_elements(current, [step], nsmap)
        if matches:
            current = matches[0]
            continue
        tag = _step_tag(step, nsmap)
        if tag is None:
            raise ValueError(f"can not create the wildcard step {step.raw}")
        current = _new_child(current, step.raw, tag,
                             element_order=element_order)
        _seed_predicate(current, step, nsmap)
    return current


def _new_sibling(after, tag):
    """Create *tag* directly after *after*, keeping the line indentation."""
    el = etree.Element(tag)
    after.addnext(el)
    el.tail = after.tail
    return el


def create_mapped_row(container, steps, nsmap, element_order=None, after=None):
    """One new row of a mapped collection.

    Without *after* the row is built below *container* at the schema position.
    With *after* - the last row the document already carries - the new row is
    inserted right beside it: a collection which spans several containers
    (several MD_Keywords blocks) is read in document order, and a row appended
    to the first container would answer a different position when read back.
    Unlike ensure_mapped_element every step is created - the row is asked for
    beside the rows the document already carries, not as another value written
    into the first one.
    """
    el = container if after is None else None
    for step in steps:
        if step.name == ".":
            continue
        tag = _step_tag(step, nsmap)
        if tag is None:
            raise ValueError(f"can not create the wildcard step {step.raw}")
        if el is None:
            el = _new_sibling(after, tag)
        else:
            el = _new_child(el, step.raw, tag, element_order=element_order)
        _seed_predicate(el, step, nsmap)
    return el


def get_mapped_value(el, attr):
    """The current text or attribute value an element carries for a path.

    *attr* is the resolved attribute name (see resolve_write_qname) or None for a
    text path; the text is answered unstripped - it is the value the reader
    extracted, so the skip-if-equal comparison sees both sides identically.
    """
    if attr:
        return el.get(attr)
    return el.text


def set_mapped_value(el, attr, value):
    """Write the value as text or attribute; a None value clears it."""
    if attr:
        if value is None:
            el.attrib.pop(attr, None)
        else:
            el.set(attr, str(value))
    else:
        el.text = None if value is None else str(value)


def remove_mapped_element(el, stop_at):
    """Remove *el* and every ancestor which lost its only meaning with it.

    The tail whitespace travels to the previous sibling so the surrounding
    lines of a pretty-printed document keep their indentation; the climb stops
    at stop_at, which keeps the record itself in any case.
    """
    tail = el.tail
    parent = el.getparent()
    if tail and parent is not None:
        prev = el.getprevious()
        if prev is not None:
            prev.tail = (prev.tail or "") + tail
        else:
            parent.text = (parent.text or "") + tail
    if parent is not None:
        parent.remove(el)
        remove_empty_parents(parent, stop_at)


def place_mapped_fragment(base_el, fragment, steps, nsmap,
                          element_order=None):
    """Place a serialized fragment at the element its path names.

    The inverse of reading a fragment field (a geometry, a nested reference):
    the fragment takes the place of the element the steps name below
    *base_el* - the first match is replaced in place, keeping the surrounding
    indentation, and a missing path is created up to its container, which
    then carries the fragment as the child the schema order names. A fragment
    that does not satisfy its last step raises: the next read would not find
    what this write wrote.
    """
    if not steps or steps[-1].name == ".":
        raise ValueError("a fragment path must name an element")
    last = steps[-1]
    if last.predicate:
        if not _predicate_holds(fragment, last.predicate, nsmap):
            raise ValueError(
                f"fragment {fragment.tag} does not satisfy step {last.raw}")
    elif _step_tag(last, nsmap) != fragment.tag:
        raise ValueError(
            f"fragment {fragment.tag} is not the element {last.raw}")
    matches = find_mapped_elements(base_el, steps, nsmap)
    if matches:
        element = matches[0]
        parent = element.getparent()
        if parent is None:  # pragma: no cover - paths never address the root
            raise ValueError("can not replace the document root")
        fragment.tail = element.tail
        parent.replace(element, fragment)
        return fragment
    container = ensure_mapped_element(
        base_el, steps[:-1], nsmap, element_order=element_order)
    container.append(fragment)
    if element_order:
        _place_ordered(container, fragment, element_order)
    prev = fragment.getprevious()
    fragment.tail = prev.tail if prev is not None else container.text
    return fragment
