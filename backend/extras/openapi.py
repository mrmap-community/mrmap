from rest_framework.fields import empty
from rest_framework_json_api import serializers
from rest_framework_json_api.schemas.openapi import AutoSchema
from rest_framework_json_api.serializers import ManyRelatedField
from rest_framework_json_api.utils import (format_field_name,
                                           get_related_resource_type)


class CustomAutoSchema(AutoSchema):
    """
    Extend DRF's openapi.AutoSchema for JSON:API serialization.
    """

    def get_related_field_object_description(self, field) -> dict:
        description = {
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",  # type of the id
                    "description": "The id of the related object",
                    # uuid pattern if uuid is pk
                    # "pattern": "[0-9a-f]{12}4[0-9a-f]{3}[89ab][0-9a-f]{15}\Z"
                },
                "type": {
                    "type": "string",
                    "description": "The related resource name",
                }
            },
            "required": [
                "id",
                "type"
            ]
        }

        description["properties"]["type"].update({"enum": [
            get_related_resource_type(relation=field)
        ]})

        return description

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
                relationships[format_field_name(
                    field.field_name)] = self.get_related_field_object_description(field=field)
                continue
            if isinstance(field, serializers.ManyRelatedField):
                relationships[format_field_name(field.field_name)] = {
                    "type": "array",
                    "items": self.get_related_field_object_description(field=field)
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
