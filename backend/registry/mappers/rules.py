"""The ISO structural profile rules and their evaluation on the resulting document (#1243).

The rule set of a metadata profile is data on the profile row (#1240), not
code: `MetadataProfile.rules` carries a list of rule objects and serving them
to the editor is the ordinary json:api attribute of the profile resource
(Q1 option C on #1243: attribute-level constraints keep riding the OpenAPI
schema, the ISO structural rules travel on the profile). This module defines
the shape of those rule objects and answers which of them a document violates.

A rule is a dict:

    {
        "id":       "iso19139-title",        # stable id, cited in the finding
        "family":   "iso19139",              # the rule SET this rule belongs
                                             # to; GDI-DE and INSPIRE join as
                                             # data with their own families,
                                             # not as code branches
        "severity": "error" | "warning",     # an error blocks the save, a
                                             # warning never does
        "field":    "title" | None,          # the record field the finding
                                             # points at (None -> /data)
        "assert":   "<XPath 1.0 boolean>",   # must hold over the document
        "message":  "<what is wrong>"        # the finding's detail
    }

The `assert` is written in the prefix-independent `local-name()` form, like
the factory's own node lookup: a document is free to bind the ISO namespaces
to any prefixes, and the same expression must evaluate in the browser
(#1245's findings rail pre-validates with exactly these rules), where DOM
XPath 1.0 has no access to the document's prefix table either.

The save-time evaluation runs over the RESULTING ISO document - the record's
document with the patched values written through the write mapper of #1242 -
never over a disconnected representation (readiness clarification of #1243).
`overlay_write_values` below converts what a record write patches into the
shape `write_mapped_values` consumes; fields it can not convert keep their
extracted rows, which is sound because a rule may only name a field the
overlay can convert (or a document field the payload can not write at all) -
`assessable_rule` is the single place that decides what the evaluator dares
to evaluate, and anything else stays fail-closed like since #1241: an
unevaluated rule set must never answer a payload as validated.
"""

from collections import namedtuple
from copy import deepcopy
from logging import Logger

from django.conf import settings
from django.utils.translation import gettext_lazy as _
from lxml import etree
from lxml.etree import XMLSyntaxError
from lxml.etree import XPathEvalError
from rest_framework_json_api.utils import format_field_name

logger: Logger = settings.ROOT_LOGGER

#: the severities a rule may name; `error` blocks the save, `warning` never
SEVERITIES = ("error", "warning")
#: the severity a rule whose engine call itself broke is answered with: a
#: rule that could not run has no verdict, and no verdict must not pass
CRASH_SEVERITY = "error"

#: the record fields whose patched value the overlay can convert into the
#: shape the write mapper reads: scalar fields pass through, the three
#: contact FKs become the dict of the four configured contact fields, the
#: keyword / language / category / reference system M2M lists become one row
#: per instance as the reader answers them.
OVERLAYABLE_FIELDS = frozenset({
    "title", "abstract", "charset", "update_frequency_code",
    "access_constraints", "equivalent_scale", "ground_res",
    "metadata_contact", "dataset_contact", "application_contact",
    "keywords", "languages", "categories", "reference_systems",
    # the extent fields of #1246: both answer a serializable fragment
    # through their config's _reverse_parser, so the write mapper can
    # carry the row's values into the document
    "bounding_geometry", "time_extents",
})

#: the fields a rule may still name although no payload can patch them:
#: their state in the document IS their state (the write mapper carries the
#: extracted rows through unchanged), so evaluating them is honest.
DOCUMENT_ONLY_FIELDS = frozenset({"date_stamp", "file_identifier"})

#: everything `assessable_rule` accepts as a rule target
RULE_FIELDS = OVERLAYABLE_FIELDS | DOCUMENT_ONLY_FIELDS

#: the four contact fields the record configs read from a CI_ResponsibleParty
_CONTACT_FIELDS = ("name", "person_name", "phone", "email")

#: sentinel of "this value can not be overlaid"; the extracted row stays
_UNCHANGED = object()

#: one rule did not hold (or could not run) over the resulting document
RuleFinding = namedtuple(
    "RuleFinding", ("rule", "family", "severity", "field", "detail"))


def assessable_rule(rule):
    """Whether this rule object is evaluable at all (fail-closed guard, #1241).

    A rule the running version can not assess - wrong shape, unknown
    severity, a field the overlay can not place into the values the write
    mapper reads - makes a whole rule set unassessable: refusing the write
    is the only answer that never presents an unevaluated rule as validated.
    """
    if not isinstance(rule, dict):
        return False
    if not all(isinstance(rule.get(key), str) and rule.get(key)
               for key in ("id", "family", "severity", "assert", "message")):
        return False
    if rule["severity"] not in SEVERITIES:
        return False
    field = rule.get("field")
    return field is None or field in RULE_FIELDS


def evaluate_rules(rules, xml):
    """Evaluate one profile rule set over an ISO document.

    :param rules: the rule dicts of the profile (all must pass
        `assessable_rule` - the caller refuses otherwise)
    :param xml: the document to evaluate, bytes (the RESULTING document at a
        save, see the module docstring)
    :returns: list of RuleFinding for every rule that did not hold
    """
    root = etree.fromstring(xml)
    findings = []
    for rule in rules:
        try:
            verdict = root.xpath(rule["assert"])
        except (XPathEvalError, XMLSyntaxError):
            # never surface engine text: the traceback belongs to the log,
            # the curator gets the rule id (acceptance criterion of #1243,
            # the failure GeoNetwork shows its curators)
            logger.exception(
                "profile rule %s could not be evaluated against the record "
                "document", rule["id"])
            findings.append(RuleFinding(
                rule=rule["id"], family=rule["family"],
                severity=CRASH_SEVERITY, field=rule.get("field"),
                detail=_(
                    "The validation rule %(rule)s could not be evaluated; "
                    "the server log carries the reason.")
                % {"rule": rule["id"]}))
            continue
        # an assertion is a boolean XPath; a node-set expression holds when
        # it selects something, which is how schematron reads its test
        if isinstance(verdict, bool):
            holds = verdict
        elif isinstance(verdict, list):
            holds = bool(verdict)
        else:
            # a count()/string() scalar: 0 and "" are the false answers
            holds = bool(verdict)
        if not holds:
            findings.append(RuleFinding(
                rule=rule["id"], family=rule["family"],
                severity=rule["severity"], field=rule.get("field"),
                detail=rule["message"]))
    return findings


def findings_to_errors(findings, status="400"):
    """The json:api error objects of a refused save (#1245's findings rail).

    Every finding answers as one custom error object (the shape
    djangorestframework-jsonapi passes through verbatim): `source.pointer`
    names the field the editor jumps to, `rule` cites the rule id so the
    client can match its own copy of the rule, `severity` says how the
    finding grades, and `meta` carries the rule family plus the severity
    counts per family of the whole run - the grouping the rail renders.
    The counts are STRINGS: a raised payload travels through DRF's
    `ValidationError` wrapping, whose `ErrorDetail` is a string subclass
    that re-renders every nested int as `"1"` anyway, and JSON:API error
    members are strings; the client compares text, not number type.
    """
    counts = {}
    for finding in findings:
        family = counts.setdefault(
            finding.family, dict.fromkeys(SEVERITIES, 0))
        family[finding.severity] += 1
    counted = {
        family: {severity: str(n) for severity, n in severities.items()}
        for family, severities in counts.items()}
    # errors first, then warnings, stable per family and rule id; the
    # library still sorts the final array by pointer, grouping is what the
    # meta carries, not the order
    ordered = sorted(
        findings, key=lambda f: (f.severity != "error", f.family, f.rule))
    errors = []
    for finding in ordered:
        pointer = ("/data" if finding.field is None
                   else f"/data/attributes/{format_field_name(finding.field)}")
        errors.append({
            "status": status,
            "source": {"pointer": pointer},
            "detail": str(finding.detail),
            "rule": finding.rule,
            "severity": finding.severity,
            "meta": {"family": finding.family, "severityCounts": counted},
        })
    return errors


def overlay_write_values(values, attrs):
    """Overlay the fields a record write patches onto an extracted record.

    :param values: the `values` dict of the record's extracted entry
        (extract_mapped_values); modified in place
    :param attrs: the serializer's validated data of the write
    :returns: None - fields whose value can not be converted keep the row
        the extraction answered, which is sound because a rule only ever
        names a field the overlay can convert or a document-only field
        (see `assessable_rule`)
    """
    for name, value in attrs.items():
        if name not in OVERLAYABLE_FIELDS:
            # not a field of the mapped document (profile, contacts of the
            # relation bookkeeping, ...) or not convertible: its extracted
            # row already is the document's own state
            continue
        converted = _convert_value(name, value)
        if converted is not _UNCHANGED:
            values[name] = converted


def _convert_value(name, value):
    """One patched value in the shape the write mapper reads."""
    if value is None or isinstance(value, (str, int, float, bool)):
        # the scalar form of every plain mapped field; None keeps the row by
        # the write mapper's own rule (None never blanks, never deletes)
        return value
    if name in ("metadata_contact", "dataset_contact", "application_contact"):
        # the config answers a contact as the dict of its four fields
        return {field: getattr(value, field, "") for field in _CONTACT_FIELDS}
    if name == "keywords":
        return [{"keyword": keyword.keyword} for keyword in value]
    if name == "languages":
        return [{"value": language.value} for language in value]
    if name == "categories":
        return [{"value": category.value} for category in value]
    if name == "reference_systems":
        # the row the extraction answers is the pair the parser split out of
        # the code text; the write serializes it back through the spec's
        # _reverse_parser
        return [{"code": system.code, "prefix": system.prefix}
                for system in value]
    if name == "bounding_geometry":
        # the row answers the model geometry and the validated payload has
        # been parsed into one; the spec's _reverse_parser turns it into the
        # bounding box or polygon fragment the path names (#1246)
        from django.contrib.gis.geos import GEOSGeometry
        return value if isinstance(value, GEOSGeometry) else _UNCHANGED
    if name == "time_extents":
        # rows arrive as instances (the row, the validated relationship);
        # answer the dict shape the extraction answered, which is what
        # _write_row_values pairs by position (#1246)
        from registry.models.metadata import TimeExtent
        rows = value if isinstance(value, (list, tuple)) else [value]
        return [
            {"begin": row.begin, "end": row.end,
             "resolution": row.resolution, "is_relative": row.is_relative}
            for row in rows if isinstance(row, TimeExtent)
        ]
    return _UNCHANGED


def copy_record(record):
    """A detached copy of one extracted record, safe to overlay onto."""
    copied = dict(record)
    copied["values"] = deepcopy(record["values"])
    return copied
