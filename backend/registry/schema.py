"""drf-spectacular schema customisation of the registry (#1240).

`inject_iso_paths` is a POSTPROCESSING_HOOKS entry (wired in
`MrMap/settings.py`): it stamps the ISO 19139 element path of every WRITABLE
mapped field of a metadata record onto that field's OpenAPI property as the
extension ``x-iso-path``. The paths come out of the mapper configs through
`registry.mappers.paths`, so the schema document and the harvest keep
reading one and the same mapping (#981/#982: one ISO interpretation layer)
and no editor carries a second, hardcoded copy of it.

Which properties get a path is decided by the schema itself: a property that
is not in the component, or is marked ``readOnly``, is not offered for
writing and gets no path. That is how "every writable field exposes its
element" and "generated forms never offer file_identifier/date_stamp/origin/
is_broken" (acceptance criteria of #1240) become one and the same rule.

The attribute-level constraints (maxLength/pattern/required) of the same
properties keep riding the plain schema — that pipeline exists end-to-end
and Q1 option C on #1243 kept it deliberately out of the profile resource.
"""

from rest_framework_json_api.utils import format_field_name

from registry.mappers.paths import RECORD_TYPE_BY_MODEL, iso_field_paths

#: the OpenAPI extension carrying the ISO 19139 element path of a field
ISO_PATH_EXTENSION = "x-iso-path"

#: the json:api resource component names of the three record resources (the
#: component name is the resource type, which is the model name);
#: COMPONENT_SPLIT_REQUEST makes spectacular emit a plain and a request
#: component per resource ("Request" for PUT, "Patched<...>Request" for
#: PATCH); the response components only $ref the plain one, so annotating
#: these three covers every record schema in the document. The mapping to
#: the record type is the mapper configs' own (``RECORD_TYPE_BY_MODEL``).
_RECORD_COMPONENTS = RECORD_TYPE_BY_MODEL


def _request_component_names(name):
    return {
        name,
        f"{name}Request",
        f"Patched{name}Request",
    }


def _properties_of(component):
    """The attribute and relationship property maps of a record component.

    The plain resource component carries its properties under
    ``properties.attributes`` / ``properties.relationships``; the request
    components nest the whole resource under the json:api ``data`` envelope.
    Both shapes answer their property maps here.
    """
    properties = component.get("properties") or {}
    if "data" in properties and isinstance(properties["data"], dict):
        properties = properties["data"].get("properties") or {}
    yield from (
        (properties.get("attributes") or {}).get("properties") or {},
        (properties.get("relationships") or {}).get("properties") or {},
    )


def inject_iso_paths(result, **kwargs):
    """Stamp ``x-iso-path`` onto the writable mapped fields of the records.

    Called by spectacular as a POSTPROCESSING_HOOK. Returns the same schema
    document it received, extended in place.
    """
    components = (result.get("components") or {}).get("schemas") or {}
    paths_by_name = {
        record_type: _served_form(record_type)
        for record_type in set(_RECORD_COMPONENTS.values())
    }
    for name, record_type in _RECORD_COMPONENTS.items():
        for component_name in _request_component_names(name):
            component = components.get(component_name)
            if not component:
                continue
            for properties in _properties_of(component):
                for property_name, property_schema in properties.items():
                    if not isinstance(property_schema, dict) or property_schema.get("readOnly"):
                        continue
                    path = paths_by_name[record_type].get(property_name)
                    if path is not None:
                        property_schema[ISO_PATH_EXTENSION] = path
    return result


def _served_form(record_type):
    """The config paths keyed by the names the schema gives its properties.

    json:api answers attribute and relationship names camelCased; the mapper
    configs speak the model's snake_case — this is that single translation.
    """
    return {
        format_field_name(field_name): path
        for field_name, path in iso_field_paths(record_type).items()
    }
