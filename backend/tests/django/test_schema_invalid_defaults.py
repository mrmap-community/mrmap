"""The served OpenAPI document documents no default that contradicts its field.

Issue #1335 measured that the served document carries this member:

    components/schemas/MetadataContact/properties/attributes/properties/email
    -> {"type": "string", "format": "email", "default": "", "title": "E-Mail", ...}

and expected the document to validate against the OpenAPI 3.0.3 schema it
declares. The validator of the issue's reproduction command reports the same
defect on every member where a documented default contradicts the value space
documented on the very node: ``""`` is not an email, it is not one of the
ReferenceSystem ``prefix`` choices (``["EPSG"]``), and it fails the
``minLength: 1`` the request side of the blank-intolerant contact fields
documents. All of them have the same source: ModelSerializer documents the
empty-string default of the model fields (``registry/models/metadata.py`` and
``registry/models/service.py``).

The fix decided in #1335 is the first option of the issue - leave the
contradicting ``default`` out of the document (``CustomOperationId`` in
``extras/schema.py``) and keep the constraints. These tests pin that decision:

* no node of the whole document documents a default that its own format, enum
  or minLength rejects (the class of the defect, not just the reported field),
* the reported email member and the discovered siblings are still documented
  with format / enum / minLength - the fix omits defaults, it does not drop
  constraints to dodge the validator,
* the serializer's own default stays untouched: ``""`` remains what the runtime
  fills in when the attribute is omitted, only the contract stops presenting it
  as a value the field accepts.
"""
from django.test import SimpleTestCase
from drf_spectacular.generators import SchemaGenerator
from registry.serializers.metadata import MetadataContactSerializer

#: members the fix removes the default from, by component and key path; the
#: first three are #1335's report, the rest are the same defect the scan over
#: the issue's reproduction document found (ReferenceSystem choices and the
#: request minLength of the blank-intolerant contact fields)
REPORTED_MEMBERS = {
    "MetadataContact": [
        "properties", "attributes", "properties", "email", "format", "email"],
    "MetadataContactRequest": [
        "properties", "data", "properties", "attributes", "properties",
        "email", "format", "email"],
    "PatchedMetadataContactRequest": [
        "properties", "data", "properties", "attributes", "properties",
        "email", "format", "email"],
    "ReferenceSystemDefault": [
        "properties", "attributes", "properties", "prefix", "enum", ["EPSG"]],
    "MetadataContactRequest.name": [
        "properties", "data", "properties", "attributes", "properties",
        "name", "minLength", 1],
}


def _dig(node, keys):
    for key in keys:
        node = node[key]
    return node


def _contradicts(node):
    """True when a node documents a default its own constraint excludes."""
    if not isinstance(node, dict) or "default" not in node:
        return False
    default = node["default"]
    if default == "" and (node.get("format") or node.get("minLength")):
        return True
    if "enum" in node and default not in node["enum"]:
        return True
    return False


def _walk_nodes(node, path=""):
    """Every (path, object member) of the generated document, for the scan."""
    if isinstance(node, list):
        for idx, item in enumerate(node):
            yield from _walk_nodes(item, f"{path}/{idx}")
    elif isinstance(node, dict):
        yield path, node
        for key, value in node.items():
            yield from _walk_nodes(value, f"{path}/{key}")


class SchemaInvalidDefaultsTests(SimpleTestCase):
    """The generated contract, run against the whole urlconf like /api/schema."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.schema = SchemaGenerator().get_schema(public=True)

    def test_no_member_documents_a_default_it_excludes(self):
        """A validator enforces each node's keywords on its default too
        (the issue's reproduction command does); a node whose default fails
        its own format / enum / minLength makes the whole document invalid."""
        offenders = sorted(
            path for path, node in _walk_nodes(self.schema)
            if _contradicts(node))
        self.assertEqual(
            offenders, [],
            f"{len(offenders)} schema members document a default their own "
            f"constraint excludes: {offenders}")

    def test_reported_members_keep_their_constraint_without_their_default(self):
        """The fix left the contradicting defaults out - it did not drop the
        constraints (format, choices, minLength) to dodge the validator.
        Key path is component -> member -> constraint keyword -> pinned
        constraint value; the member itself must no longer carry 'default'."""
        components = self.schema["components"]["schemas"]
        for name, spec in REPORTED_MEMBERS.items():
            component = components[name.split(".")[0]]
            member = _dig(component, spec[:len(spec) - 2])
            keyword, value = spec[-2:]
            self.assertEqual(member.get(keyword), value, name)
            self.assertNotIn("default", member, name)

    def test_the_serializer_default_stays_the_empty_string(self):
        """This is a document fix, not a behavior change: ModelSerializer
        still fills "" when the attribute is omitted - that is the model
        field's own default and the API keeps answering what it stored."""
        self.assertEqual(
            MetadataContactSerializer().fields["email"].default, "")
