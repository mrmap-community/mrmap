"""The served OpenAPI document answers structured labels with its choices.

Issue #1487 measured how the frontend recovered enum choices: it parsed
them out of the description PROSE drf-spectacular generates
("``* `0` - Fatal``") — the only place the schema layer depended on the
library's wording, so an i18n or rendering change upstream silently dropped
the SelectInput choices it built. The fix is on the emitting side
(``extras/schema.py``): every documented enum of a choices field answers
``x-enum-labels`` — ``[{"value": <enum value>, "label": <display>}]`` —
and the postprocessing hook moves the labels into the enum components
``postprocess_schema_enums`` extracts, because a sibling of ``$ref`` is
invisible to OpenAPI consumers.

These tests pin the served contract:

* every node that documents an enum together with the choices prose also
  answers labels — no enum is left readable from prose only,
* the label values are exactly the values of that enum minus the blank and
  null members, which are documented structurally and are no choice,
* the issue's example: the choice set of ``LogLevelEnum`` answers the
  model's own labels (``0`` -> ``Fatal``),
* no label sits beside a ``$ref``, where no consumer could see it, and an
  ``allOf`` wrapper site answers the same labels as the component it names.
"""
from django.test import SimpleTestCase
from drf_spectacular.generators import SchemaGenerator
from extras.schema import ENUM_LABELS_EXTENSION
from registry.enums.harvesting import LogLevelEnum

#: one line of the prose drf-spectacular appends to a choices field's
#: description: ``* `value` - label``, standalone or after the help text
PROSE_START = "* `"


def _nodes(node, path=""):
    """Every (path, object member) of the generated document."""
    if isinstance(node, list):
        for idx, item in enumerate(node):
            yield from _nodes(item, f"{path}/{idx}")
    elif isinstance(node, dict):
        yield path, node
        for key, value in node.items():
            yield from _nodes(value, f"{path}/{key}")


def _documents_choices_prose(node):
    """True when the node documents an enum and the choices prose with it."""
    if "enum" not in node:
        return False
    description = node.get("description")
    if not isinstance(description, str):
        return False
    return (description.startswith(PROSE_START)
            or f"\n\n{PROSE_START}" in description)


def _label_values(node):
    return [entry.get("value")
            for entry in node.get(ENUM_LABELS_EXTENSION) or []]


class SchemaEnumLabelsTests(SimpleTestCase):
    """The generated contract, run against the whole urlconf like /api/schema."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.schema = SchemaGenerator().get_schema(public=True)

    def test_every_choice_enum_answers_its_labels_beside_the_values(self):
        """An enum documented with the prose choice list must answer the same
        data structured — a consumer shall never have to parse the wording."""
        missing = []
        mismatched = []
        for path, node in _nodes(self.schema):
            if not _documents_choices_prose(node):
                continue
            labels = node.get(ENUM_LABELS_EXTENSION)
            if not isinstance(labels, list):
                missing.append(path)
                continue
            # blank and null members are no choice: the emission excludes
            # them (spectacular reconstructs them structurally, the frontend
            # contract could never use them) — the labels never mention them
            expected = [v for v in node["enum"] if v not in ("", None)]
            if _label_values(node) != expected:
                mismatched.append(
                    f"{path}: {_label_values(node)} != {expected}")
        self.assertEqual(
            missing, [],
            f"{len(missing)} enum members document their choices in prose "
            f"only, without {ENUM_LABELS_EXTENSION}: {missing}")
        self.assertEqual(
            mismatched, [],
            f"{len(mismatched)} label sets do not answer their enum exactly")

    def test_no_label_is_left_beside_a_ref(self):
        """OpenAPI ignores the siblings of a $ref and the frontend
        dereferencer drops them — a label only helps inside the component."""
        offenders = sorted(
            path for path, node in _nodes(self.schema)
            if isinstance(node.get("$ref"), str)
            and ENUM_LABELS_EXTENSION in node)
        self.assertEqual(
            offenders, [],
            f"{len(offenders)} $ref members still carry {ENUM_LABELS_EXTENSION} "
            f"as a sibling: {offenders}")

    def test_the_issue_example_answers_the_log_level_labels(self):
        """``0` - Fatal` is the log level choice set of the issue: the enum
        member answering those values answers the model's labels."""
        expected = [{"value": value, "label": str(label)}
                    for value, label in LogLevelEnum.choices]
        expected_values = [entry["value"] for entry in expected]
        answers = [
            (path, node[ENUM_LABELS_EXTENSION])
            for path, node in _nodes(self.schema)
            if isinstance(node.get(ENUM_LABELS_EXTENSION), list)
            and _label_values(node) == expected_values]
        self.assertTrue(
            answers,
            "no documented enum answers the values of LogLevelEnum — the "
            "anchor of this contract disappeared from the document")
        self.assertTrue(
            any(labels == expected for _path, labels in answers),
            f"no member answers the log level values with "
            f"{expected}: {answers}")

    def test_a_wrapper_site_and_its_component_answer_the_same_labels(self):
        """A property composed as ``allOf: [ref]`` keeps its labels for the
        consumer reading the property AND stamps the same ones onto the
        component — a drifted copy would lie to one of them."""
        schemas = self.schema["components"]["schemas"]
        drift = []
        for path, node in _nodes(self.schema):
            labels = node.get(ENUM_LABELS_EXTENSION)
            if not isinstance(labels, list) or "$ref" in node:
                continue  # direct siblings were moved away (test above)
            refs = {
                item["$ref"] for item in node.get("allOf") or ()
                if isinstance(item, dict)
                and isinstance(item.get("$ref"), str)}
            if len(refs) != 1:
                continue
            component = schemas.get(next(iter(refs)).rpartition("/")[2])
            if (isinstance(component, dict)
                    and component.get(ENUM_LABELS_EXTENSION) != labels):
                drift.append(path)
        self.assertEqual(
            drift, [],
            f"{len(drift)} allOf wrapper sites answer other labels than the "
            f"component they reference: {drift}")
