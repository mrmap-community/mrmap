"""The served WFS version is refused by the API, not by a crashed task (#1210).

The GetCapabilities URI validator of the create serializers listed WFS 1.1.0 and
1.0.0 as supported, while the mappers ship no capabilities config for any 1.x:
the POST was accepted and the registration task died with a bare IndexError on
the empty mapping, visible only to whoever polled the background process. What
is pinned here: versions without a mapping config are answered with a 400 that
names version and protocol, the versions the WFS 2.0.0 config really maps
(2.0.0 and, through the shared /wfs/2.0 namespace, 2.0.2) stay accepted, and the
WMS answer of the same validator is untouched by this change.
"""
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from extras.validators import validate_get_capablities_uri
from registry.models.service import WebFeatureService
from rest_framework.test import APIClient

JSONAPI = "application/vnd.api+json"


def capabilities_url(service, version):
    return ("http://some-service.de/service?SERVICE="
            f"{service}&VERSION={version}&REQUEST=GetCapabilities")


class CapabilitiesVersionValidatorTest(TestCase):
    """The URI validator only names versions a mapping config can actually read."""

    def assert_refused(self, url, expected_fragment):
        with self.assertRaises(ValidationError) as ctx:
            validate_get_capablities_uri(url)
        messages = " ".join(str(message) for message in ctx.exception.messages)
        self.assertIn(expected_fragment, messages)

    def test_wfs_versions_without_mapping_config_are_refused(self):
        # 1.3.0 was already refused before #1210 and stays the baseline
        for version in ("1.3.0", "1.1.0", "1.0.0"):
            with self.subTest(version=version):
                self.assert_refused(
                    capabilities_url("WFS", version),
                    f"wfs version {version} is not supported")

    def test_wfs_versions_mapped_by_the_2_0_0_config_pass(self):
        # 2.0.2 shares the /wfs/2.0 namespace with the shipped config
        for version in ("2.0.0", "2.0.2"):
            with self.subTest(version=version):
                validate_get_capablities_uri(capabilities_url("WFS", version))

    def test_wms_answer_of_the_validator_is_unchanged(self):
        # #1210 only narrows WFS; the WMS versions the validator accepted
        # before keep passing so no WMS registration policy moves with it
        for version in ("1.3.0", "1.1.1"):
            with self.subTest(version=version):
                validate_get_capablities_uri(capabilities_url("WMS", version))


class WfsRegistrationApiTest(TestCase):
    """`POST /api/registry/wfs` refuses an unmappable version up front."""

    fixtures = ["test_users.json", "test_organizations.json"]

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(
            get_user_model().objects.get(username="User1"))
        self.client.credentials(HTTP_ACCEPT=JSONAPI)

    def post_url(self, version):
        return self.client.post("/api/registry/wfs", {
            "data": {
                "type": "WebFeatureService",
                "attributes": {
                    "get_capabilities_url": capabilities_url("WFS", version),
                },
                "relationships": {
                    "owner": {"data": {"id": "901", "type": "Organization"}},
                },
            }
        }, format="vnd.api+json")

    def test_unsupported_version_is_answered_with_400(self):
        response = self.post_url("1.1.0")
        self.assertEqual(response.status_code, 400, response.content)
        details = " ".join(
            str(error.get("detail")) for error in response.json()["errors"])
        self.assertIn("wfs version 1.1.0", details)
        self.assertIn("not supported", details)
        self.assertEqual(
            WebFeatureService.objects.count(), 0,
            msg="a refused registration may not leave a service behind")
