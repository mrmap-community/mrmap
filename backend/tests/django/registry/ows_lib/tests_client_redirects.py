"""The redirect budget of the OGC client (#1100).

An endpoint which redirects back at itself walked the 30 hops the session allows before it
raised - on every retry of a harvest - and the abort named neither the URL it walked nor the
target it stopped at. The client answers such a chain with a sentence naming both.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from django.conf import settings
from django.test import SimpleTestCase
from registry.ows_lib.client import core
from registry.ows_lib.client.core import MAX_REDIRECTS
from registry.ows_lib.client.exceptions import RedirectChainError
from registry.ows_lib.csw.csw import CatalogueServiceClient
from requests import Request, Session
from requests.exceptions import RequestException


class OgcClientRedirectTest(SimpleTestCase):
    """the walk of the client against a catalogue which answers with redirects"""

    def setUp(self):
        self.requested = []
        self.methods = []
        # the Locations this catalogue answers with, one per request; an empty list answers
        # with the document, `loop` answers with the same login page for every request
        self.locations = []
        self.loop = False
        self.status = 302
        self.body = (
            b'<csw:GetRecordsResponse xmlns:csw="http://www.opengis.net/cat/csw/2.0.2">'
            b'<csw:SearchResults numberOfRecordsMatched="6952"/>'
            b'</csw:GetRecordsResponse>')
        test = self

        class Handler(BaseHTTPRequestHandler):
            def answer(self):
                test.methods.append(self.command)
                test.requested.append(self.path)
                length = int(self.headers.get('Content-Length') or 0)
                if length:
                    self.rfile.read(length)
                location = test.locations.pop(0) if test.locations else (
                    '/csw/login.html' if test.loop else None)
                body = b'redirecting' if location else test.body
                self.send_response(test.status if location else 200)
                if location:
                    self.send_header('Location', location)
                self.send_header('Content-Type', 'application/xml')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                self.answer()

            def do_POST(self):
                self.answer()

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.addCleanup(server.server_close)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(server.shutdown)
        session = Session()
        session.trust_env = False
        self.addCleanup(session.close)
        capabilities = Path(
            settings.BASE_DIR, 'tests/django/test_data/capabilities/csw/2.0.2.xml').read_bytes()
        self.client = CatalogueServiceClient(capabilities, session=session)
        self.url = f'http://127.0.0.1:{server.server_port}/csw'
        self.origin = self.url[:len(self.url) - len('/csw')]

    def test_a_redirect_of_the_same_host_is_followed(self):
        """a catalogue which answers the endpoint with its own path is a working catalogue"""
        self.locations = ['/csw/']
        response = self.client.send_request(Request('GET', self.url), timeout=2)
        self.assertEqual(response.content, self.body)
        self.assertEqual(self.requested, ['/csw', '/csw/'])

    def test_relative_targets_are_resolved_over_the_whole_chain(self):
        """the client asks for every hop itself, so a relative Location must still be resolved
        against the URL of the hop which named it, the way the session resolves it"""
        self.locations = ['/a', '/b/', '/csw/document']
        response = self.client.send_request(Request('GET', self.url), timeout=2)
        self.assertEqual(self.requested, ['/csw', '/a', '/b/', '/csw/document'])
        self.assertEqual(response.content, self.body)

    def test_the_method_of_a_303_is_rebuilt_for_the_next_hop(self):
        """a 303 names its target for GET; the client relies on the prepared request of the
        session for that, because it walks the hops one by one"""
        self.status = 303
        self.locations = ['/csw/']
        self.client.send_request(Request('POST', self.url, data=b'<query/>'), timeout=2)
        self.assertEqual(self.methods, ['POST', 'GET'])

    def test_a_self_redirecting_catalogue_stops_at_the_budget_of_the_client(self):
        """the endpoint of the four catalogues of #1100: the walk ends after the hops the
        client allows, not after the 30 the session walks by default"""
        self.loop = True
        with self.assertRaises(RedirectChainError):
            self.client.send_request(Request('GET', self.url), timeout=2)
        self.assertEqual(len(self.requested), MAX_REDIRECTS + 1)
        self.assertLess(len(self.requested), 30)

    def test_the_abort_names_the_requested_url_and_the_last_target(self):
        """the harvest answers the abort with the name and the message of the error, so this
        message is what an operator reads instead of "Exceeded 30 redirects" (#1100)"""
        self.loop = True
        with self.assertRaises(RedirectChainError) as raised:
            self.client.send_request(Request('GET', self.url), timeout=2)
        detail = str(raised.exception)
        self.assertIn(self.url, detail)
        self.assertIn(f'{self.origin}/csw/login.html', detail)

    def test_a_hop_which_leaves_the_host_of_the_endpoint_is_not_asked(self):
        """a CSW endpoint which lands on the login page of another host is not a CSW
        endpoint, and asking that host is not the business of this harvest"""
        for target in ('http://geodienste.example.de/csw/login.html', 'file:///etc/passwd'):
            with self.subTest(target=target):
                self.requested.clear()
                self.locations = [target]
                with self.assertRaises(RedirectChainError) as raised:
                    self.client.send_request(Request('GET', self.url), timeout=2)
                self.assertEqual(self.requested, ['/csw'])
                self.assertIn(target, str(raised.exception))

    def test_a_refusal_which_carries_a_location_is_not_walked(self):
        """a provider which refuses the request and names another page in the same answer - the
        refusal of the four catalogues of #1100 - is answered by that refusal: the run reads a
        refusal and does not walk to the page the answer points at"""
        self.status = 429
        self.locations = ['/csw/login.html']
        response = self.client.send_request(Request('GET', self.url), timeout=2)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(self.requested, ['/csw'])

    def test_a_redirect_chain_is_no_retryable_request_error(self):
        """a redirect chain is decided by the endpoint and answers identically on every retry,
        so it must not be one of the request errors a harvest retries (#1100)"""
        self.assertFalse(issubclass(RedirectChainError, RequestException))


class RedirectHostTest(SimpleTestCase):
    """the guard which refuses a hop out of the endpoint compares hosts, not URLs (#1100)"""

    def test_the_scheme_of_a_redirect_may_change(self):
        """an endpoint registered as http is served over https the same way, and naming the
        default port of the scheme says nothing more about it"""
        origin = core._host_of('http://cat.example.de/csw')
        self.assertEqual(core._host_of('https://cat.example.de/csw/login.html'), origin)
        self.assertEqual(core._host_of('http://cat.example.de:80/csw'), origin)
        self.assertEqual(core._host_of('https://cat.example.de:443/csw'), origin)

    def test_another_host_or_port_is_not_the_endpoint(self):
        origin = core._host_of('http://cat.example.de/csw')
        self.assertNotEqual(core._host_of('http://geodienste.example.de/csw'), origin)
        self.assertNotEqual(core._host_of('http://cat.example.de:8443/csw'), origin)

    def test_a_url_naming_no_port_is_compared_by_its_host_alone(self):
        self.assertEqual(core._host_of('http://cat.example.de/csw'),
                         core._host_of('http://CAT.Example.DE/csw?SERVICE=CSW'))

    def test_a_malformed_port_names_no_host(self):
        self.assertIsNone(core._host_of('http://cat.example.de:not-a-port/csw'))
