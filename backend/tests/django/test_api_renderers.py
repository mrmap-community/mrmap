"""Renderer configuration of the REST API (#751).

A production deployment must not answer the browsable API; a development
deployment keeps it. The browsable renderer renders an HTML page for any API
response and is a development facility.

The negotiation of a running instance can not be measured with
``override_settings``: DRF binds ``APIView.renderer_classes`` to
``api_settings.DEFAULT_RENDERER_CLASSES`` while the view classes are imported,
so an override applied afterwards never reaches them - which is the kind of
test override the issue warns about. The probes below therefore run a
subprocess which loads ``MrMap.settings`` the way a deployment does, with
``MRMAP_PRODUCTION`` and ``DJANGO_DEBUG`` given in its environment.
"""

import json
import os
import subprocess
import sys
import tempfile

from django.conf import settings
from django.test import SimpleTestCase

from MrMap import settings as mrmap_settings

BROWSABLE_RENDERER = "BrowsableAPIRendererWithoutForms"
JSON_RENDERER = "JSONRenderer"
BROWSABLE_RENDERER_PATH = "extras.utils.BrowsableAPIRendererWithoutForms"
JSON_RENDERER_PATH = "extras.renderers.JSONRenderer"

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

#: Separates the probe's report from the log output of the deployment.
REPORT_MARKER = "MRMAP_RENDERERS_PROBE "

#: Read only endpoints which answer without a fixture of their own.
PUBLIC_ENDPOINT = "/api/system/info"
ADMINISTRATOR_ENDPOINT = "/api/system/status/current"

DEPLOYMENT_PROBE = '''
import json
import os
import sys

# settings.py detects a test run from argv, which keeps the debug toolbar out of
# the configuration the probe measures. The deployment mode itself comes from
# the environment, exactly like in a running deployment.
sys.argv = ["manage.py", "test"]
os.environ["DJANGO_SETTINGS_MODULE"] = "MrMap.settings"

import django

django.setup()

from django.conf import settings  # noqa: E402
from django.test import Client  # noqa: E402
from rest_framework.settings import api_settings  # noqa: E402
from system.views import SystemStatusView  # noqa: E402

MARKER = "%(marker)s"
PUBLIC = "%(public)s"
ADMINISTRATOR = "%(administrator)s"
JSONAPI_ACCEPT = "application/vnd.api+json"


def ask(url, **extra):
    response = Client().get(url, **extra)
    content_type = response.headers.get("Content-Type", "")
    return {
        "status": response.status_code,
        "content_type": content_type,
        "is_html": "text/html" in content_type,
    }


report = {
    "production": settings.MRMAP_PRODUCTION,
    "debug": bool(settings.DEBUG),
    "renderer_classes": [r.__name__ for r in api_settings.DEFAULT_RENDERER_CLASSES],
    "view_renderer_classes": [r.__name__ for r in SystemStatusView.renderer_classes],
    "jsonapi": ask(PUBLIC, HTTP_ACCEPT=JSONAPI_ACCEPT),
    "any": ask(PUBLIC, HTTP_ACCEPT="*/*"),
    "no_accept": ask(PUBLIC),
    "html": ask(PUBLIC, HTTP_ACCEPT="text/html"),
    "browsable_format": ask(PUBLIC + "?format=api"),
    "anonymous_json": ask(ADMINISTRATOR, HTTP_ACCEPT=JSONAPI_ACCEPT),
    "anonymous_html": ask(ADMINISTRATOR, HTTP_ACCEPT="text/html"),
}
sys.stdout.write(MARKER + json.dumps(report) + "\\n")
'''


def run_deployment_probe(production, debug=True):
    """Ask a deployment instance of the given mode what it answers.

    Loads ``MrMap.settings`` in a fresh interpreter, so the answer is the
    configuration of a production or development instance and not of a test
    settings module which already forces JSON only renderers.
    """
    environment = dict(os.environ)
    environment["MRMAP_PRODUCTION"] = "True" if production else "False"
    environment["DJANGO_DEBUG"] = "1" if debug else "0"
    script = DEPLOYMENT_PROBE % {
        "marker": REPORT_MARKER,
        "public": PUBLIC_ENDPOINT,
        "administrator": ADMINISTRATOR_ENDPOINT}
    descriptor, script_path = tempfile.mkstemp(
        suffix=".py", dir=BACKEND_DIR, text=True)
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(script)
        completed = subprocess.run(
            [sys.executable, script_path], cwd=BACKEND_DIR, env=environment,
            capture_output=True, text=True, timeout=300)
    finally:
        os.unlink(script_path)
    if completed.returncode != 0 or REPORT_MARKER not in completed.stdout:
        raise AssertionError(
            "the deployment probe did not report:\n"
            f"{completed.stdout}\n{completed.stderr}")
    return json.loads(
        completed.stdout.split(REPORT_MARKER, 1)[1].splitlines()[0])


class RendererConfigurationTests(SimpleTestCase):
    """The registered renderers depend on the deployment mode."""

    def test_the_loaded_configuration_matches_the_loaded_production_flag(self):
        self.assertEqual(
            settings.REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"],
            mrmap_settings.default_renderer_classes(mrmap_settings.MRMAP_PRODUCTION))

    def test_production_configuration_registers_only_the_json_renderer(self):
        self.assertEqual(
            mrmap_settings.default_renderer_classes(production=True),
            [JSON_RENDERER_PATH])

    def test_development_configuration_keeps_the_browsable_renderer(self):
        self.assertEqual(
            mrmap_settings.default_renderer_classes(production=False),
            [BROWSABLE_RENDERER_PATH, JSON_RENDERER_PATH])


class ProductionDeploymentTests(SimpleTestCase):
    """A production deployment - with debug enabled by accident."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.report = run_deployment_probe(production=True, debug=True)

    def test_the_probed_deployment_is_a_production_with_debug(self):
        self.assertTrue(self.report["production"])
        self.assertTrue(self.report["debug"])

    def test_no_browsable_renderer_is_registered(self):
        self.assertNotIn(BROWSABLE_RENDERER, self.report["renderer_classes"])
        self.assertEqual(self.report["renderer_classes"], [JSON_RENDERER])
        # A view resolves its renderers while it is imported, so this is what
        # the endpoints of that deployment actually answer with.
        self.assertEqual(self.report["view_renderer_classes"], [JSON_RENDERER])

    def test_jsonapi_accept_header_is_answered_as_before(self):
        answered = self.report["jsonapi"]
        self.assertEqual(answered["status"], 200)
        self.assertEqual(answered["content_type"], "application/vnd.api+json")

    def test_any_accept_is_answered_with_the_api_representation(self):
        answered = self.report["any"]
        self.assertEqual(answered["status"], 200)
        self.assertFalse(answered["is_html"])

    def test_request_without_accept_header_is_answered_in_json(self):
        answered = self.report["no_accept"]
        self.assertEqual(answered["status"], 200)
        self.assertFalse(answered["is_html"])

    def test_html_only_request_is_rejected_instead_of_browsed(self):
        answered = self.report["html"]
        self.assertEqual(answered["status"], 406)
        self.assertFalse(answered["is_html"])

    def test_the_browsable_format_override_can_not_render_the_api_browser(self):
        """DRF answers an unknown renderer format with 404, never with HTML."""
        answered = self.report["browsable_format"]
        self.assertEqual(answered["status"], 404)
        self.assertFalse(answered["is_html"])

    def test_permissions_are_not_changed_by_the_renderer_configuration(self):
        """The refused anonymous client is answered in JSON:API, not in HTML."""
        answered = self.report["anonymous_json"]
        self.assertIn(answered["status"], (401, 403))
        self.assertFalse(answered["is_html"])
        self.assertEqual(answered["content_type"], "application/vnd.api+json")
        answered = self.report["anonymous_html"]
        self.assertIn(answered["status"], (401, 403, 406))
        self.assertFalse(answered["is_html"])


class DevelopmentDeploymentTests(SimpleTestCase):
    """The development convenience of the browsable API stays untouched."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.report = run_deployment_probe(production=False, debug=True)

    def test_the_probed_deployment_is_not_production(self):
        self.assertFalse(self.report["production"])

    def test_the_browsable_renderer_is_registered(self):
        self.assertEqual(
            self.report["renderer_classes"],
            [BROWSABLE_RENDERER, JSON_RENDERER])

    def test_an_html_request_still_browses_the_api(self):
        answered = self.report["html"]
        self.assertEqual(answered["status"], 200)
        self.assertTrue(answered["is_html"])

    def test_the_browsable_format_override_still_browses_the_api(self):
        answered = self.report["browsable_format"]
        self.assertEqual(answered["status"], 200)
        self.assertTrue(answered["is_html"])

    def test_the_api_representation_is_reachable_as_before(self):
        answered = self.report["jsonapi"]
        self.assertEqual(answered["status"], 200)
        self.assertEqual(answered["content_type"], "application/vnd.api+json")
