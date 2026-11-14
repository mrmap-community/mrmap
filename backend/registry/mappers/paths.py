"""ISO 19139 element paths of the mapped fields of a record (#1240).

The configs in `registry/mappers/configs/` are the one ISO interpretation
layer of mrmap (#981/#982): they say, per record type and per model field,
which elements of the document the mapper reads - and, once #1242 extends
them, writes back to. This module asks those configs the inverse question of
the editor: which element does this writable field stand for? It only
re-reads the configured paths and joins the relative ones onto the
configured bases; it parses no XML, walks no tree and defines no mapping of
its own, which is what keeps it from becoming a second interpretation layer.

What it answers for one record type (`dataset`, `service`, `application`):

* a plain string field maps to its configured xpath;
* a field with several `_inputs` maps to the first of them: the primary
  element the mapper reads, the remaining fallbacks stay a reading detail
  and are no place to write to;
* a nested model entry (a relationship such as `keywords` or
  `metadata_contact`) maps to its `_base_xpath`: the element one related row
  is created under;
* a `_values` entry is skipped - online links, operations and coupling
  evidence carry no model field of the record and answer no field of its
  serializer;
* the `_pre_save` keys and the namespace bookkeeping of the config are not
  fields and never enter the answer.

The configured paths are served verbatim, with one normalisation: a `./`
step is only XPath for "same node", joining a base `/gmd:MD_Metadata` onto
`./gmd:contact` reads `/gmd:MD_Metadata/gmd:contact` - keeping the `./` in
the served string would make every consumer parse it away itself.
"""

#: the resource key each record model maps through, mirroring the second
#: level of `XPATH_MAP` of the configs: ("ISO", <key>) is the config, its
#: resource entry is named by the third element of the tuple used nowhere
#: else than as the nesting key.
RECORD_TYPE_BY_MODEL = {
    "DatasetMetadataRecord": "dataset",
    "ServiceMetadataRecord": "service",
    "ApplicationMetadataRecord": "application",
}


def _join(base, relative):
    """Append a configured relative path to the configured base path.

    `./x` and `x` are the same location seen from the base; the served form
    is the single-slash join of both.
    """
    return f"{base.rstrip('/')}/{relative.lstrip('./').lstrip('/')}"


def iso_field_paths(record_type):
    """Map every configured field name of one record type to its element path.

    :param record_type: one of `dataset`, `service`, `application`
    :returns: dict keyed by the model field name of the record, holding the
        absolute XPath the mapper config gives that field
    """
    # imported here: the configs read `registry.ows_lib` consts, which need
    # the app registry; the function runs at schema generation, never at
    # module import of the schema hook
    from registry.mappers.configs import application, dataset, service

    config_by_type = {
        "dataset": dataset.XPATH_MAP,
        "service": service.XPATH_MAP,
        "application": application.XPATH_MAP,
    }
    xpath_map = config_by_type[record_type]
    paths = {}
    for config in xpath_map.values():
        for resource in config.values():
            if not isinstance(resource, dict) or "_model" not in resource:
                continue
            paths.update(_resource_field_paths(resource))
    return paths


def _resource_field_paths(resource):
    """The field paths of one mapped resource of the config.

    One resource per config today; looping the fields rather than assuming
    the shape keeps the answer of this module the config's own.
    """
    base = resource["_base_xpath"]
    paths = {}
    for field_name, field in resource.get("fields", {}).items():
        if isinstance(field, str):
            paths[field_name] = _join(base, field)
        elif not isinstance(field, dict):
            continue
        elif "_values" in field:
            # no model field, no serializer field: reading evidence only
            continue
        elif "_inputs" in field:
            paths[field_name] = _join(base, field["_inputs"][0])
        elif "_model" in field and "_base_xpath" in field:
            paths[field_name] = _join(base, field["_base_xpath"])
    return paths
