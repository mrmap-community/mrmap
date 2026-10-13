from django.test import SimpleTestCase
from django.urls import resolve
from rest_framework.test import APIRequestFactory


class NestedServiceSchemaTests(SimpleTestCase):

    def test_nested_service_operations_do_not_replace_normal_list_operations(self):
        from django.urls import include, path
        from drf_spectacular.generators import SchemaGenerator
        from registry.urls import urlpatterns

        names = {"wms-list", "wfs-list", "servicemetadata-wms-list", "servicemetadata-wfs-list"}
        patterns = [pattern for pattern in urlpatterns if getattr(pattern, "name", None) in names]
        schema = SchemaGenerator(patterns=[path("api/registry/", include(patterns))]).get_schema(public=True)
        for protocol, resource in (("wms", "WebMapService"), ("wfs", "WebFeatureService")):
            with self.subTest(protocol=protocol):
                operation = schema["paths"][f"/api/registry/{protocol}"]["get"]
                self.assertEqual(operation["operationId"], f"list_{resource}")
                self.assertFalse(any(param["in"] == "path" for param in operation.get("parameters", [])))
                nested = schema["paths"][f"/api/registry/service-metadata/{{ServiceMetadataRecordId}}/{protocol}"]["get"]
                self.assertEqual(nested["operationId"], f"list_related_{resource}_of_ServiceMetadataRecord")
                self.assertEqual([param["name"] for param in nested["parameters"] if param["in"] == "path"], ["ServiceMetadataRecordId"])

    def test_nested_service_lists_return_not_found_for_invalid_parent_ids(self):
        for protocol in ("wms", "wfs"):
            with self.subTest(protocol=protocol):
                url = f"/api/registry/service-metadata/undefined/{protocol}"
                request = APIRequestFactory().get(url, HTTP_ACCEPT="application/vnd.api+json")
                callback, _, kwargs = resolve(url)
                response = callback(request, **kwargs)
                response.render()
                self.assertEqual(response.status_code, 404)
