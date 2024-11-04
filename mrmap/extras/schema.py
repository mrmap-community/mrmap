from django.urls import resolve
from django.urls.exceptions import Resolver404
from drf_spectacular.plumbing import get_view_model
from drf_spectacular_jsonapi.schemas.openapi import JsonApiAutoSchema
from extras.viewsets import NestedModelViewSet
from rest_framework_gis.fields import GeometryField
from rest_framework_gis.filters import GeometryFilter
from rest_framework_json_api.utils import get_resource_name


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

                    if isinstance(field, GeometryFilter):
                        openapiparameter = next(
                            (param for param in res if param["name"] == f"filter[{field_name}]"), None)
                        if openapiparameter:
                            schema = openapiparameter.get(
                                "schema", {"type": "string"})
                            schema["format"] = "geojson"
                            openapiparameter["schema"] = schema

        return res
