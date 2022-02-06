from rest_framework.fields import empty
from rest_framework_json_api import serializers, views
from rest_framework_json_api.schemas.openapi import AutoSchema
from rest_framework_json_api.utils import (format_field_name,
                                           get_related_resource_type,
                                           get_resource_type_from_serializer)


class CustomAutoSchema(AutoSchema):
    """
    Extend DRF's openapi.AutoSchema for JSON:API serialization.
    """

    def get_related_field_object_description(self, field) -> dict:
        description = {
            "type": "object",
            "properties": {
                # TODO: here should be the concrete id object... uuid, bigint, etc...
                "id": {"$ref": "#/components/schemas/id"},
                "type": {
                    "type": "string",
                    "description": "The related resource name",
                    "enum": [get_related_resource_type(relation=field)]
                },
            },
            "required": [
                "id",
                "type"
            ]
        }

        return description

    def get_request_body(self, path, method):
        """
        A request body is required by JSON:API for POST, PATCH, and DELETE methods.
        """
        serializer = self.get_serializer(path, method)
        if not isinstance(serializer, (serializers.BaseSerializer,)):
            return {}
        is_relationship = isinstance(self.view, views.RelationshipView)

        # DRF uses a $ref to the component schema definition, but this
        # doesn't work for JSON:API due to the different required fields based on
        # the method, so make those changes and inline another copy of the schema.
        # TODO: A future improvement could make this DRYer with multiple component schemas:
        #   A base schema for each viewset that has no required fields
        #   One subclassed from the base that requires some fields (`type` but not `id` for POST)
        #   Another subclassed from base with required type/id but no required attributes (PATCH)

        if is_relationship:
            item_schema = {
                "$ref": "#/components/schemas/ResourceIdentifierObject"}
        else:
            item_schema = self.map_serializer(serializer)
            if method == "POST":
                # 'type' and 'id' are both required for:
                # - all relationship operations
                # - regular PATCH or DELETE
                # Only 'type' is required for POST: system may assign the 'id'.
                item_schema["required"] = ["type"]
            if method in ["POST", "PATCH", "DELETE"]:
                del item_schema["properties"]["links"]

        if "properties" in item_schema and "attributes" in item_schema["properties"]:
            # No required attributes for PATCH
            if (
                method in ["PATCH", "PUT"]
                and "required" in item_schema["properties"]["attributes"]
            ):
                del item_schema["properties"]["attributes"]["required"]
            # No read_only fields for request.
            for name, schema in (
                item_schema["properties"]["attributes"]["properties"].copy().items()
            ):  # noqa E501
                if "readOnly" in schema:
                    del item_schema["properties"]["attributes"]["properties"][name]
        return {
            "content": {
                ct: {
                    "schema": {
                        "required": ["data"],
                        "properties": {"data": item_schema},
                    }
                }
                for ct in self.content_types
            }
        }

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
                # TODO: handle nullable with anyOf [1: "#/components/schemas/nulltype", ...]
                d = self.get_related_field_object_description(field=field)
                if field.help_text:
                    # Ensure django gettext_lazy is rendered correctly
                    d["description"] = str(field.help_text)
                if field.label:
                    # Ensure django gettext_lazy is rendered correctly
                    d["title"] = str(field.label)
                relationships[format_field_name(field.field_name)] = d
                continue
            if isinstance(field, serializers.ManyRelatedField):
                # TODO: handle nullable with anyOf [1: "#/components/schemas/nulltype", ...]
                d = {
                    "type": "array",
                    "items": self.get_related_field_object_description(field=field)
                }
                if field.help_text:
                    # Ensure django gettext_lazy is rendered correctly
                    d["description"] = str(field.help_text)
                if field.label:
                    # Ensure django gettext_lazy is rendered correctly
                    d["title"] = str(field.label)
                relationships[format_field_name(field.field_name)] = d
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
                # Ensure django gettext_lazy is rendered correctly
                schema["title"] = str(field.label)
            self.map_field_validators(field, schema)

            attributes[format_field_name(field.field_name)] = schema

        result = {
            "type": "object",
            "required": ["type", "id"],
            "additionalProperties": False,
            "properties": {
                "type": {
                    "type": "string",
                    "description": "The related resource name",
                    "enum": [get_resource_type_from_serializer(serializer=serializer)]
                },
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
