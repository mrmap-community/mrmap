from rest_framework.fields import empty
from rest_framework_json_api import serializers
from rest_framework_json_api.schemas.openapi import AutoSchema
from rest_framework_json_api.utils import format_field_name


class CustomAutoSchema(AutoSchema):
    """
    Extend DRF's openapi.AutoSchema for JSON:API serialization.
    """

    def map_serializer(self, serializer):
        """
        Custom map_serializer that serializes the schema using the JSON:API spec.
        Non-attributes like related and identity fields, are move to 'relationships' and 'links'.
        """
        # TODO: remove attributes, etc. for relationshipView??
        required = []
        attributes = {}
        relationships = {}

        for field in serializer.fields.values():
            if isinstance(field, serializers.HyperlinkedIdentityField):
                # the 'url' is not an attribute but rather a self.link, so don't map it here.
                continue
            if isinstance(field, serializers.HiddenField):
                continue
            if isinstance(field, serializers.RelatedField):
                # TODO: here should be the ref to the concrete linked component schema definition... outerwise an automatic usage is not possible
                relationships[format_field_name(field.field_name)] = {
                    "$ref": "#/components/schemas/reltoone"
                }
                continue
            if isinstance(field, serializers.ManyRelatedField):
                # TODO: here should be the ref to the concrete linked component schema definition... outerwise an automatic usage is not possible
                relationships[format_field_name(field.field_name)] = {
                    "$ref": "#/components/schemas/reltomany"
                }
                continue

            if field.required:
                required.append(format_field_name(field.field_name))

            schema = self.map_field(field)
            if field.read_only:
                schema["readOnly"] = True
            if field.write_only:
                schema["writeOnly"] = True
            if field.allow_null:
                schema["nullable"] = True
            if field.default and field.default != empty:
                schema["default"] = field.default
            if field.help_text:
                # Ensure django gettext_lazy is rendered correctly
                schema["description"] = str(field.help_text)
            if field.label:
                schema["title"] = str(field.label)
            self.map_field_validators(field, schema)

            attributes[format_field_name(field.field_name)] = schema

        result = {
            "type": "object",
            "required": ["type", "id"],
            "additionalProperties": False,
            "properties": {
                # TODO: here should be the ref to the concrete type... outerwise an automatic usage is not possible
                "type": {"$ref": "#/components/schemas/type"},
                # TODO: here should be the concrete id object... uuid, bigint, etc...
                "id": {"$ref": "#/components/schemas/id"},
                # TODO: links are not needed for post, patch, delete
                "links": {
                    "type": "object",
                    "properties": {"self": {"$ref": "#/components/schemas/link"}},
                },
            },
        }
        if attributes:
            result["properties"]["attributes"] = {
                "type": "object",
                "properties": attributes,
            }
            if required:
                result["properties"]["attributes"]["required"] = required

        if relationships:
            result["properties"]["relationships"] = {
                "type": "object",
                "properties": relationships,
            }
        return result
