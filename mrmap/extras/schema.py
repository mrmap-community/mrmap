from drf_spectacular_jsonapi.schemas.openapi import JsonApiAutoSchema
from rest_framework_json_api.utils import get_resource_name


class Schema(JsonApiAutoSchema):
    def get_operation_id(self):
        resoruce_name = get_resource_name({"view": self.view})
        if self.method == 'GET' and self._is_list_view():
            action = 'list'
        else:
            action = self.method_mapping[self.method.lower()]
        return f"{action}_{resoruce_name}"
