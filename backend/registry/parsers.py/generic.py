
import importlib

from django.apps import apps
from lxml import etree
from registry.parsers.service import (  # oder via dynamic loading
    bbox_to_polygon, polygon_to_bbox)


def load_function(dotted_path):
    module_path, func_name = dotted_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, func_name)


def get_model_class(model_path: str):
    return apps.get_model(model_path)


def parse_element(xml_elem, mapping: dict, parent_instance=None, namespaces=None):
    """
    Rekursiver Parser, der:
    - einfache XPath → Text Felder
    - dict mit _inputs/_parser → Spezialfeld
    - dict mit _xpath/_model → Liste von Unterobjekten
    """
    data = {}
    for key, spec in mapping.items():
        if key.startswith("_"):
            continue

        # Spezialfälle
        if isinstance(spec, dict) and "_inputs" in spec and "_parser" in spec:
            # Sammle die Werte
            values = []
            for xpath_expr in spec["_inputs"]:
                res = xml_elem.xpath(xpath_expr, namespaces=namespaces)
                if not res:
                    values.append(None)
                else:
                    # Ob Attribut oder Elementtext
                    node = res[0]
                    if isinstance(node, etree._ElementUnicodeResult) or isinstance(node, etree._ElementStringResult):
                        # Wenn Attribut oder direkte Text
                        values.append(str(node))
                    elif hasattr(node, "text"):
                        values.append(node.text)
                    else:
                        values.append(str(node))
            parser_func = load_function(spec["_parser"])
            try:
                parsed = parser_func(values)
            except Exception as e:
                # Logging oder Fallback
                parsed = None
                # z. B. logger.error(...)
            data[key] = parsed

        elif isinstance(spec, dict) and "_xpath" in spec and "_model" in spec:
            # Liste von Unterobjekten
            model_cls = get_model_class(spec["_model"])
            sub_elems = xml_elem.xpath(spec["_xpath"], namespaces=namespaces)
            children = []
            for sub in sub_elems:
                child_data = parse_element(sub, {k: v for k, v in spec.items(
                ) if not k.startswith("_")}, parent_instance=None, namespaces=namespaces)
                # Set parent FK wenn nötig
                # z.B. wenn model_cls hat field service or layer
                if parent_instance:
                    # find FK
                    # Beispielannahme: model_cls hat ein FK-Feld auf parent_instance.__class__
                    fk_field = None
                    for f in model_cls._meta.get_fields():
                        if f.is_relation and f.related_model == parent_instance.__class__:
                            fk_field = f.name
                            break
                    if fk_field:
                        child_data[fk_field] = parent_instance
                child_instance = model_cls(**child_data)
                # hier evtl .save() oder bulk_create später
                child_instance.save()
                children.append(child_instance)
            data[key] = children

        else:
            # einfacher XPath → String/Text
            if isinstance(spec, str):
                res = xml_elem.xpath(spec, namespaces=namespaces)
                if res:
                    node = res[0]
                    if hasattr(node, "text"):
                        data[key] = node.text
                    else:
                        data[key] = str(node)
                else:
                    data[key] = None
            else:
                # unbekannter Typ
                data[key] = None

    return data
