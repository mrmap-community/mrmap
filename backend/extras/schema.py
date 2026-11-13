from django.core.exceptions import FieldError
from django.db.models import ForeignKey
from django.db.models.sql.query import Query
from django.urls import resolve
from django.urls.exceptions import Resolver404
from django.utils.translation import gettext_lazy as _
from drf_spectacular.plumbing import get_view_model
from drf_spectacular_jsonapi.schemas.openapi import JsonApiAutoSchema
from rest_framework.filters import OrderingFilter as DRFOrderingFilter
from rest_framework_gis.fields import GeometryField
from rest_framework_gis.filters import GeometryFilter
from rest_framework_json_api.utils import (format_field_name,
                                           get_resource_name,
                                           get_resource_type_from_model)

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


# ``solve_lookup_type`` is a pure function of (model, lookup) and the
# generation of one document asks it ~1900 times for a handful of models;
# the same holds for the related-field inventory of a model. Both are
# memoized per process — the schema is generated from the deployed code,
# which is fixed for the lifetime of the process.
_LOOKUP_MEMO = {}
_RELATED_FIELDS_MEMO = {}
_FIELDS_LOOKUP_MEMO = {}


def _solve_filter_lookup(model, lookup):
    key = (model, lookup)
    result = _LOOKUP_MEMO.get(key)
    if result is None:
        result = Query(model).solve_lookup_type(lookup)
        _LOOKUP_MEMO[key] = result
    return result


def _fields_lookup_of_model(model):
    """Every name the ORM resolves through this model: its own columns, the
    reverse relations and the m2m — the vocabulary a filter path starts
    from. Pure ``_meta`` reading, so it is taken once per model."""
    fields_lookup = _FIELDS_LOOKUP_MEMO.get(model)
    if fields_lookup is None:
        fields = {
            concrete_field.name: concrete_field
            for concrete_field in model._meta.concrete_fields
        }
        reverse_rel_fields = {
            rel.get_accessor_name(): rel
            for rel in model._meta.related_objects
        }
        m2m_fields = {
            m2m.name: m2m
            for m2m in model._meta.local_many_to_many
        }
        fields_lookup = _FIELDS_LOOKUP_MEMO[model] = (
            fields | reverse_rel_fields | m2m_fields)
    return fields_lookup


class CustomOperationId(JsonApiAutoSchema):

    def get_operation_id(self):
        if self.method == 'GET' and self._is_list_view():
            action = 'list'
        else:
            action = self.method_mapping[self.method.lower()]
        resource_name = get_resource_name(context={"view": self.view})

        # the viewsets are asked of here and not imported at the top: this module
        # is what DEFAULT_SCHEMA_CLASS names, and drf-spectacular resolves that
        # setting while a view module is being imported — a viewset which
        # declares a schema with @extend_schema would otherwise close the circle
        from extras.viewsets import NestedModelViewSet
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

        # A documented default that contradicts the value space documented on
        # the very field breaks every consumer that validates the contract
        # against it (#1335): "" is not an email, it is not one of a field's
        # choices and it fails a minLength of 1. The members come from
        # ModelSerializer documenting the empty-string default of the model
        # fields; that default stays the runtime behaviour of the API - only
        # the self-contradicting member is left out of the document. The
        # constraints themselves are kept: they tell a client which values the
        # field accepts, and a default that fits them is still documented.
        if "default" in schema:
            default = schema["default"]
            if (
                default == "" and (schema.get("format") or schema.get("minLength"))
            ) or (
                "enum" in schema and default not in schema["enum"]
            ):
                del schema["default"]
        return schema

    def _get_related_fields_of_model(self, model):
        related_fields = _RELATED_FIELDS_MEMO.get(model)
        if related_fields is None:
            related_fields = {}
            for field in model._meta.get_fields():
                if isinstance(field, ForeignKey):
                    related_fields[field.name] = field
            for rel in model._meta.related_objects:
                related_fields[rel.related_query_name] = rel
            for m2m in model._meta.local_many_to_many:
                related_fields[m2m.name] = m2m
            _RELATED_FIELDS_MEMO[model] = related_fields
        # the only caller reads it; hand out the shared mapping
        return related_fields

    def _patch_extend_filter_parameter(self, field, parameter):
        model = get_view_model(self.view)
        # lookup_parts is an array of parts but it is limited to only one possible lookup expression
        try:
            fields_lookup = _fields_lookup_of_model(model)
            lookup_parts, field_parts, expression = _solve_filter_lookup(
                model, field.field_name)

            if field_parts[0] in fields_lookup:

                model_field = fields_lookup[field_parts[0]]
                if hasattr(model_field, "related_model") and model_field.related_model:
                    last_seen_model = model_field.related_model

                    for idx, part in enumerate(field_parts):
                        # analyze the full path so we get the correct resource type for the filter parameter, in case of nested relationships
                        if idx == 0:
                            parameter["x-jsonapi-related-resource-field"] = format_field_name(
                                part)
                            continue
                        related_fields = self._get_related_fields_of_model(
                            last_seen_model)
                        if part in related_fields:
                            last_seen_model = related_fields[part].related_model
                            parameter["x-jsonapi-related-resource-field"] = format_field_name(
                                related_fields[part].target_field.name)
                        else:
                            parameter["x-jsonapi-related-resource-field"] = format_field_name(
                                part)
                            break

                    parameter["x-jsonapi-related-resource-type"] = get_resource_type_from_model(
                        last_seen_model)

                if hasattr(field, "lookup_expr"):
                    parameter["x-jsonapi-filter-lookup-expression"] = field.lookup_expr

                parameter["x-jsonapi-field-parts"] = [
                    format_field_name(part) for part in field_parts]
                parameter["x-jsonapi-local-resource-field"] = format_field_name(
                    field_parts[0])

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
        self._restore_undocumented_sort_parameter(res)
        return res

    def _restore_undocumented_sort_parameter(self, parameters):
        """Document `sort` for list views whose ordering fields are implicit.

        JsonApiAutoSchema drops the `sort` parameter whenever the view has no
        explicit `ordering_fields`. That assumes such an endpoint rejects
        sorting, but the json:api OrderingFilter is still in the default
        filter backends: without `ordering_fields` DRF validates `sort`
        against the serializer fields (get_default_valid_fields) and answers
        400 for anything else. The parameter is therefore enforced but hidden
        from the contract. Re-add it with the same enum the filter accepts, so
        the schema describes the enforced contract instead of hiding it.
        """
        if any(parameter.get("name") == "sort" for parameter in parameters):
            return
        for filter_backend in self.get_filter_backends():
            if not issubclass(filter_backend, DRFOrderingFilter):
                continue
            enum = self._implicit_sort_enum(filter_backend())
            if not enum:
                continue
            for parameter in filter_backend().get_schema_operation_parameters(self.view):
                if parameter.get("name") != "sort":
                    continue
                parameter["schema"] = {
                    "type": "array",
                    "items": {"type": "string", "enum": enum},
                }
                parameter["explode"] = False
                parameters.append(parameter)
            return

    def _implicit_sort_enum(self, backend):
        """The terms a json:api OrderingFilter accepts when the view declares
        no `ordering_fields`, formatted as clients send them. None when the
        fallback cannot be resolved without a request (no class queryset);
        then nothing is documented, which is the pre-existing state."""
        if getattr(self.view, "ordering_fields", None) is not None:
            return None
        queryset = getattr(self.view, "queryset", None)
        if queryset is None:
            return None
        try:
            valid_fields = backend.get_valid_fields(queryset, self.view, {})
        except Exception:  # a view DRF itself could not sort at runtime
            return None
        enum = []
        for field_name, _label in valid_fields:
            term = format_field_name(field_name)
            enum.append(term)
            enum.append(f"-{term}")
        return enum

    def _patch_sort_param_schema(self, sort_param):
        """Accept tuple (or any non-str iterable) `ordering_fields` too.

        Upstream only builds the enum for a `list` or "__all__"; the tuple
        whitelists several mrmap viewsets use stay a plain string parameter,
        so clients cannot see the accepted values. Same enum shape as the
        list case.
        """
        ordering_fields = getattr(self.view, "ordering_fields", None)
        if ordering_fields is not None and not isinstance(ordering_fields, (list, str)):
            enum = []
            for field_name in ordering_fields:
                term = format_field_name(field_name)
                enum.append(term)
                enum.append(f"-{term}")
            if enum:
                sort_param["schema"]["type"] = "array"
                sort_param["schema"]["items"] = {"type": "string", "enum": enum}
                sort_param["explode"] = False
            return
        super()._patch_sort_param_schema(sort_param=sort_param)
