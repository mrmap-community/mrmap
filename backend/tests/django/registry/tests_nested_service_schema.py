from django.test import SimpleTestCase
from django.urls import Resolver404, resolve
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

    def test_wfs_preview_image_is_only_available_on_canonical_service_route(self):
        service_id = "73cf78c9-6605-47fd-ac4f-1be59265df65"
        match = resolve(f"/api/registry/wfs/{service_id}/preview-image")
        self.assertEqual(match.url_name, "wfs-preview-image")
        for url in (
                f"/api/registry/wms/{service_id}/preview-image",
                f"/api/registry/csw/{service_id}/preview-image",
                f"/api/registry/service-metadata/{service_id}/wfs/{service_id}/preview-image"):
            with self.subTest(url=url), self.assertRaises(Resolver404):
                resolve(url)

    def test_wfs_preview_schema_describes_png_and_preview_url(self):
        from django.urls import include, path
        from drf_spectacular.generators import SchemaGenerator
        from registry.urls import urlpatterns

        patterns = [pattern for pattern in urlpatterns
                    if getattr(pattern, "name", None) in {"wfs-detail", "wfs-preview-image"}]
        schema = SchemaGenerator(patterns=[path("api/registry/", include(patterns))]).get_schema(public=True)
        previews = [operation["get"] for url, operation in schema["paths"].items()
                    if url.endswith("/preview-image")]
        self.assertEqual(len(previews), 1)
        self.assertEqual(previews[0]["operationId"], "preview_image_WebFeatureService")
        content = previews[0]["responses"]["200"]["content"]
        self.assertEqual(set(content), {"image/png"})
        self.assertEqual(content["image/png"]["schema"], {"type": "string", "format": "binary"})

        def preview_url_fields(value):
            if isinstance(value, dict):
                if "previewUrl" in value.get("properties", {}):
                    yield value["properties"]["previewUrl"]
                for child in value.values():
                    yield from preview_url_fields(child)
            elif isinstance(value, list):
                for child in value:
                    yield from preview_url_fields(child)

        fields = list(preview_url_fields(schema["components"]["schemas"]))
        self.assertTrue(fields)
        for field in fields:
            self.assertEqual(field["type"], "string")
            self.assertEqual(field["format"], "uri")
            self.assertTrue(field["readOnly"])
