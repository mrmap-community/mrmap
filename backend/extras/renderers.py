from extras.utils import parse_sparse_fieldsets
from rest_framework import relations
from rest_framework.settings import api_settings
from rest_framework_json_api.renderers import JSONRenderer as BaseJSONRenderer


class JSONRenderer(BaseJSONRenderer):
    """Compare sparse fieldsets using the serializer's Python field names."""

    @classmethod
    def _filter_sparse_fields(cls, serializer, fields, resource_name):
        request = serializer.context.get('request')
        if request and f'fields[{resource_name}]' in request.query_params:
            sparse_fields = parse_sparse_fieldsets(request).get(resource_name, [])
            return {
                name: field for name, field in fields.items()
                if field.field_name in sparse_fields
                or (
                    field.field_name == api_settings.URL_FIELD_NAME
                    and isinstance(field, relations.HyperlinkedIdentityField)
                )
            }
        return fields
