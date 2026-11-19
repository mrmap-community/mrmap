"""The single canonical application version and its consumers (#1579).

Before #1579 the version was one handwritten constant in
``MrMap/__init__.py``; the acceptance made the root ``VERSION`` file the only
place a human writes it, and everything else a projection. This module pins
the projection contract from inside the runtime - exactly the context that
cannot see the root file: a backend container receives ``backend/`` as a bind
mount, so what it imports is the generated ``MrMap/version.py``, not the
canonical file. The cross-tree equality (generated file == root ``VERSION``)
is the host-side gate ``scripts/canonical_version.py --check``, run by
``scripts/test_canonical_version.py`` in CI.

What is pinned here:

* the version answers in the exact SemVer 2.0.0 grammar (prerelease and
  ``+build`` metadata are expressible, so a release candidate with an exact
  revision still names its version),
* ``MrMap.__version__`` and ``MrMap.VERSION`` stay defined (the compatibility
  surface settings, Sphinx and the ADR's four readers import),
* the OpenAPI document's ``info.version`` and the schema cache key carry it,
* the system info endpoint answers it as ``mrmap_release`` - the operator's
  "which build is this" answer, admin-only as pinned by #1445.

The runtime deliberately performs no git call and no working-directory probe
for the version; it is a committed projection that travels inside the mounted
``backend/`` tree, so these tests hold with any cwd in any container.
"""

import re

from django.contrib.auth import get_user_model
from django.test import RequestFactory, SimpleTestCase, TestCase
from rest_framework.test import APIClient

from extras.schema_views import RevalidatableOpenApiSchemaView
from MrMap import VERSION, __version__
from MrMap import settings as mrmap_settings

INFO_URL = "/api/system/info"
JSONAPI = "application/vnd.api+json"

# SemVer 2.0.0, the grammar exactly as https://semver.org defines it - the
# same pattern scripts/canonical_version.py and frontend/vite.config.mjs
# validate the root VERSION file with.
SEMVER = re.compile(
    r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)'
    r'(?:-(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*'
    r'(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?'
    r'(?:\+(?:[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$'
)


class CanonicalVersionRuntimeTests(SimpleTestCase):
    """What the backend itself answers, without git and without a cwd."""

    def test_the_version_is_strict_semver(self):
        self.assertRegex(VERSION, SEMVER)

    def test_the_historical_names_stay_defined(self):
        # settings.py does `from . import VERSION`; the docs conf imports it
        # through MrMap; the __version__ synonym is the Python convention
        self.assertEqual(__version__, VERSION)

    def test_the_openapi_document_version_is_the_canonical_version(self):
        self.assertEqual(mrmap_settings.SPECTACULAR_SETTINGS['VERSION'],
                         VERSION)

    def test_the_schema_cache_key_carries_the_version(self):
        # a version bump must invalidate the cached document; the key is how
        key = RevalidatableOpenApiSchemaView()._document_cache_key(
            RequestFactory().get('/'))
        self.assertIn(f':{VERSION}:', key)


class SystemInfoVersionTests(TestCase):
    """/api/system/info answers the canonical version to an admin (#1445)."""

    def setUp(self):
        self.admin = get_user_model().objects.create_user(
            username="version-admin", password="x", is_staff=True)

    def test_system_info_names_the_canonical_version_twice(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        response = client.get(INFO_URL, HTTP_ACCEPT=JSONAPI)
        self.assertEqual(response.status_code, 200, response.content)
        attributes = response.json()["data"]["attributes"]
        self.assertEqual(attributes["mrmapRelease"], VERSION)
        self.assertEqual(response.json()["data"]["id"], VERSION)
