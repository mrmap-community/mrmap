from attrs import field
from django.urls import resolve
from django.urls.exceptions import Resolver404
from drf_spectacular.plumbing import get_view_model
from drf_spectacular_jsonapi.schemas.openapi import JsonApiAutoSchema
from extras.viewsets import NestedModelViewSet
from rest_framework_gis.fields import GeometryField
from rest_framework_gis.filters import GeometryFilter
from rest_framework_json_api.utils import format_field_name, get_resource_name, get_resource_type_from_model
from django.db.models import ForeignKey
from django.core.exceptions import FieldError

from django.db.models.sql.query import Query
from django.utils.translation import gettext_lazy as _

LOOKUP_LABELS = {
    "exact": _("is exactly"),
    "iexact": _("is exactly (case-insensitive)"),
    "contains": _("contains"),
    "icontains": _("contains (case-insensitive)"),
    "startswith": _("starts with"),
    "istartswith": _("starts with (case-insensitive)"),
    "endswith": _("ends with"),
    "iendswith": _("ends with (case-insensitive)"),
    "gt": _("greater than"),
    "gte": _("greater than or equal to"),
    "lt": _("less than"),
    "lte": _("less than or equal to"),
    "in": _("is one of"),
    "isnull": _("is empty"),
    "range": _("is between"),
    "regex": _("matches regex"),
    "iregex": _("matches regex (case-insensitive)"),
}


class CustomOperationId(JsonApiAutoSchema):

    def get_operation_id(self):
        if self.method == 'GET' and self._is_list_view():
            action = 'list'
        else:
            action = self.method_mapping[self.method.lower()]
        resource_name = get_resource_name(context={"view": self.view})

        is_nested_view = isinstance(self.view, NestedModelViewSet)
        if is_nested_view:
            related_base_resource_path = self.path.split("{")[0]
            if related_base_resource_path.endswith("/"):
                # remove trailing slash
                # TODO: only needed if trailing_slash=False option was used
                related_base_resource_path = related_base_resource_path[:-1]
            try:
                match = resolve(related_base_resource_path)
                base_resource_name = get_resource_name(
                    context={"view": match.func.cls(action='list')})
                return f"{action}_related_{resource_name}_of_{base_resource_name}"
            except Resolver404:
                # fallback solution to provide operation ids if no view was found
                return super().get_operation_id()

        return f"{action}_{resource_name}"

    def _map_serializer_field(self, field, direction, bypass_extensions=False):
        schema = super()._map_serializer_field(
            field, direction, bypass_extensions=bypass_extensions)

        if isinstance(field, GeometryField):
            schema.pop("properties", "")
            schema["type"] = "string"
            schema["format"] = "geojson"
        return schema

    def _patch_extend_filter_parameter(self, field, parameter):
        model = get_view_model(self.view)
        # lookup_parts is an array of parts but it is limited to only one possible lookup expression
        try:
            fk_fields = {
                field.name: field
                for field in model._meta.concrete_fields
                if isinstance(field, ForeignKey)
            }
            many_fields = {
                rel.get_accessor_name(): rel
                for rel in model._meta.related_objects
            }

            fields_lookup = fk_fields | many_fields
            lookup_parts, field_parts, expression = Query(
                model).solve_lookup_type(field.field_name)

            if field_parts[0] in fields_lookup:

                model_field = fields_lookup[field_parts[0]]
                related_model_cls = model_field.related_model
                parameter["x-jsonapi-field-parts"] = [
                    format_field_name(part) for part in field_parts]
                parameter["x-jsonapi-local-resource-field"] = format_field_name(
                    field_parts[0])
                if len(field_parts) > 1:
                    parameter["x-jsonapi-related-resource-field"] = format_field_name(
                        field_parts[1])
                parameter["x-jsonapi-related-resource-type"] = get_resource_type_from_model(
                    related_model_cls)
                parameter["x-jsonapi-filter-lookup-expression"] = field.lookup_expr
                parameter["x-jsonapi-filter-lookup-expression-label"] = LOOKUP_LABELS.get(
                    field.lookup_expr, field.lookup_expr)

                label = field.label or getattr(
                    model_field, "verbose_name", None)
                if label:
                    parameter["x-jsonapi-filter-label"] = label

        except FieldError:
            pass

    def _get_filter_parameters(self):
        """
            fix to provide format information in case of GeometryFilter
        """
        res = super()._get_filter_parameters()
        model = get_view_model(self.view)
        if model:
            filterset_class = getattr(self.view, "filterset_class", None)
            if filterset_class:
                for field_name, field in filterset_class.base_filters.items():
                    openapiparameter = next(
                        (param for param in res if param["name"] == f"filter[{field_name}]"), None)
                    if not openapiparameter:
                        continue

                    self._patch_extend_filter_parameter(
                        field, openapiparameter)

                    if isinstance(field, GeometryFilter):
                        schema = openapiparameter.get(
                            "schema", {"type": "string"})
                        schema["format"] = "geojson"
                        openapiparameter["schema"] = schema
        """         
        TODO: add extension to link resource types, filteroperator, labels and help texts to the filter parameters
         e.g.:
         {
            "in": "query",
            "name": "filter[allowed_groups__user__in]",
            "schema": {
                "type": "array",
                "items": {
                "type": "string",
                "format": "uuid"
                }
            },
            "description": "Filter by related User resource IDs.",
            "x-jsonapi-resource-type": "User",
            "x-jsonapi-relation-path": "allowed_groups.user",
            "x-jsonapi-filter-operator": "in",
            "x-jsonapi-lookup-endpoint": "/api/users",
            "style": "form",
            "explode": false
            }

        """
        return res
