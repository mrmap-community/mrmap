from rest_framework import serializers as drf_serializers
from rest_framework.fields import empty
from rest_framework_json_api import serializers, views
from rest_framework_json_api.schemas.openapi import AutoSchema
from rest_framework_json_api.serializers import \
    ResourceIdentifierObjectSerializer
from rest_framework_json_api.utils import (format_field_name,
                                           get_related_resource_type,
                                           get_resource_type_from_serializer)

from extras.utils import deep_update


class CustomAutoSchema(AutoSchema):
    """
    Extend DRF's openapi.AutoSchema for JSON:API serialization.
    """

    def build_base_component(self, serializer):
        return {
            "type": "object",
            "required": ["type"],
            "properties": {
                "type": {
                    "type": "string",
                    "description": "The [type](https://jsonapi.org/format/#document-resource-object-identification) member is used to describe resource objects that share common attributes and relationships.",
                    "enum": [get_resource_type_from_serializer(serializer=serializer)]
                }
            }
        }

    def get_components(self, path, method):
        """
        Return components with their properties from the serializer.
        """

        if method.lower() == 'delete':
            return {}

        serializer = self.get_serializer(path, method)

        if not isinstance(serializer, drf_serializers.Serializer):
            return {}

        component_name = self.get_component_name(serializer)

        components = {
            f"{component_name}Base": self.build_base_component(serializer=serializer)
        }

        content = self.map_serializer(serializer, method)
        # if method.lower() == "get":
        #     properties = content.get("properties", {})
        #     properties.update({"links": {
        #         "type": "object",
        #         "properties": {"self": {"$ref": "#/components/schemas/link"}},
        #     }})

        components.update(
            {f"{component_name}{method.lower().capitalize() if method.lower() != 'get' else 'Response'}": content})
        return components

    def get_related_field_object_description(self, field) -> dict:
        description = {
            "type": "object",
            "properties": {
                "id": self.map_field(field=field),
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

    def _get_reference(self, serializer, method="Response"):
        if isinstance(serializer, ResourceIdentifierObjectSerializer):
            method = ""
        return {'$ref': f'#/components/schemas/{self.get_component_name(serializer)}{method.lower().capitalize()}'}

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
            # TODO: concrete components should be used here...
            item_schema = {
                "$ref": "#/components/schemas/ResourceIdentifierObject"}
        else:
            item_schema = self._get_reference(serializer, method)
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

    def map_serializer(self, serializer, method):
        """
        Custom map_serializer that serializes the schema using the JSON:API spec.
        Non-attributes like related and identity fields, are move to 'relationships' and 'links'.
        """
        # TODO: remove attributes, etc. for relationshipView??
        required = []
        attributes = {}
        relationships = {}
        meta = {}
        _id = {"$ref": "#/components/schemas/id"}

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

            if field.field_name in list(getattr(serializer.Meta, "meta_fields", list())):
                meta[format_field_name(field.field_name)] = schema
            else:
                attributes[format_field_name(field.field_name)] = schema

            # FIXME: this is just a primitive check of the primary key...
            if field.field_name == "id":
                _id = schema

        result = {
            "allOf": [
                {"$ref": f"#/components/schemas/{self.get_component_name(serializer)}Base"},
                {
                    "type": "object",
                }
            ],
        }

        if attributes:
            deep_update(
                d=result["allOf"][1],
                u={
                    "properties": {
                        "attributes": {
                            "type": "object",
                            "properties": attributes,
                        }
                    }
                })
        if relationships:
            deep_update(
                d=result["allOf"][1],
                u={
                    "properties": {
                        "relationships": {
                            "type": "object",
                            "properties": relationships,
                        }
                    }
                })
        if method.lower() == "get" and meta:
            deep_update(
                d=result["allOf"][1],
                u={
                    "properties": {
                        "meta": {
                            "type": "object",
                            "properties": meta,
                        }
                    }
                })

        if method.lower() in ["get", "patch"]:
            result["allOf"][1].update({"required": ["id"]})
            result["allOf"][1].update({"id": _id})
        elif method.lower() in ["post", "delete"] and attributes and required:

            deep_update(
                d=result["allOf"][1],
                u={
                    "properties": {
                        "attributes": {
                            "required": required
                        }
                    }
                })
        return result
