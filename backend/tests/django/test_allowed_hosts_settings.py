"""Host allow-list contract (#949).

The documented ``DJANGO_ALLOWED_HOSTS`` variable was never read by
``MrMap/settings.py``, was never passed by docker-compose.yml and mixed with
``EXTERNAL_BASE_URL`` and the internal ``DJANGO_ALLOWED_HOST_DEFAULTS``. A
deployment reached by any name but the EXTERNAL_BASE_URL host answered HTTP
400. These tests pin the contract: the documented variable is honored, the
internal preset and the EXTERNAL_BASE_URL host stay allowed, and the merged
list decides on the wire - a foreign Host gets a 400, a listed one is served.
"""

import os

from django.test import Client, SimpleTestCase, TestCase, override_settings

from MrMap import settings

FOREIGN_IP = '10.99.12.3'


class AllowedHostsEnvTests(SimpleTestCase):
    """``_allowed_hosts_from_env`` merges the three sources of the allow-list."""

    PRESET = settings.ALLOWED_HOSTS_PRESET.split(';')

    def test_documented_variable_is_honored(self):
        hosts = settings._allowed_hosts_from_env({'DJANGO_ALLOWED_HOSTS': FOREIGN_IP})
        self.assertIn(FOREIGN_IP, hosts)

    def test_preset_survives_the_deployer_entries(self):
        hosts = settings._allowed_hosts_from_env({'DJANGO_ALLOWED_HOSTS': 'demo.mrmap.de'})
        for host in self.PRESET:
            self.assertIn(host, hosts)

    def test_comma_semicolon_and_blanks_are_all_separators(self):
        hosts = settings._allowed_hosts_from_env(
            {'DJANGO_ALLOWED_HOSTS': 'a.example, b.example;c.example , d.example'})
        self.assertEqual(
            hosts, sorted(set(self.PRESET) | {'a.example', 'b.example', 'c.example', 'd.example'}))

    def test_empty_deployer_value_adds_nothing(self):
        # docker-compose.yml passes "${DJANGO_ALLOWED_HOSTS:-}", so an unset
        # .env value arrives as an empty string and must be a no-op
        self.assertEqual(
            settings._allowed_hosts_from_env({'DJANGO_ALLOWED_HOSTS': ''}),
            settings._allowed_hosts_from_env({}))

    def test_defaults_variable_replaces_the_preset(self):
        hosts = settings._allowed_hosts_from_env(
            {'DJANGO_ALLOWED_HOST_DEFAULTS': 'internal.svc;other.svc'})
        self.assertIn('internal.svc', hosts)
        self.assertIn('other.svc', hosts)
        self.assertNotIn('mrmap-appserver', hosts)  # replaced, not extended
        self.assertIn('localhost', hosts)  # the EXTERNAL_BASE_URL default

    def test_external_base_url_stays_auto_allowed(self):
        for url, expected in (
            ('http://localhost:8000', 'localhost'),
            ('https://demo.mrmap.de', 'demo.mrmap.de'),
            ('https://demo.mrmap.de:8443/mrmap', 'demo.mrmap.de'),
            ('mrmap.example.com', 'mrmap.example.com'),
            ('mrmap.example.com:8000', 'mrmap.example.com'),
            ('http://[::1]:8000', '[::1]'),
        ):
            hosts = settings._allowed_hosts_from_env({'EXTERNAL_BASE_URL': url})
            self.assertIn(expected, hosts, url)

    def test_deployer_entries_keep_their_port_suffix(self):
        # django allows "host:port" entries; they pass through unmodified
        hosts = settings._allowed_hosts_from_env({'DJANGO_ALLOWED_HOSTS': 'demo.mrmap.de:8000'})
        self.assertIn('demo.mrmap.de:8000', hosts)

    def test_settings_match_the_environment_they_were_built_from(self):
        self.assertEqual(settings.ALLOWED_HOSTS, settings._allowed_hosts_from_env(os.environ))

    def test_settings_keep_the_internal_callers(self):
        # the stack itself must stay reachable: dev server and health probes
        # on localhost, the ETF validator callback, the django test client
        for host in ('localhost', 'mrmap-appserver', 'testserver'):
            self.assertIn(host, settings.ALLOWED_HOSTS)


class AllowedHostsRequestTests(TestCase):
    """The merged list decides on the wire: foreign Host 400, listed host served."""

    def setUp(self):
        # the client must hand back the 400 response instead of raising
        self.client = Client(raise_request_exception=False)

    def test_foreign_host_is_answered_400(self):
        with override_settings(ALLOWED_HOSTS=['localhost']):
            response = self.client.get('/api/system/info', headers={'host': FOREIGN_IP})
        self.assertEqual(response.status_code, 400)

    @override_settings(ALLOWED_HOSTS=[FOREIGN_IP])
    def test_listed_host_is_answered(self):
        response = self.client.get('/api/system/info', headers={'host': FOREIGN_IP})
        self.assertEqual(response.status_code, 200)

    def test_default_test_host_is_answered(self):
        # no Host override: "testserver" rides the preset which settings keeps
        response = self.client.get('/api/system/info')
        self.assertEqual(response.status_code, 200)
