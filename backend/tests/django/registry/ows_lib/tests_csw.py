import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.conf import settings
from django.test import SimpleTestCase
from registry.models.harvest import HarvestingJob
from registry.ows_lib.csw.csw import CatalogueServiceClient
from registry.ows_lib.xml.consts import NAMESPACE_LOOKUP
from requests import Request, Session
from requests.exceptions import ChunkedEncodingError


class CatalogueServiceCompressionTest(SimpleTestCase):
    def setUp(self):
        self.encodings = []
        self.fallback_body = (
            b'<csw:GetRecordsResponse xmlns:csw="http://www.opengis.net/cat/csw/2.0.2">'
            b'<csw:SearchResults numberOfRecordsMatched="6952"/>'
            b'</csw:GetRecordsResponse>')
        self.fallback_status = 200
        self.truncate_fallback = False
        self.corrupt_gzip = False
        self.broken_length = True
        test = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                encoding = self.headers.get('Accept-Encoding')
                test.encodings.append(encoding)
                identity = encoding == 'identity'
                body = test.fallback_body if identity else gzip.compress(test.fallback_body)
                if not identity and test.corrupt_gzip:
                    body = b'not gzip'
                self.send_response(test.fallback_status if identity else 200)
                self.send_header('Content-Type', 'application/xml')
                if not identity:
                    self.send_header('Content-Encoding', 'gzip')
                truncated = test.truncate_fallback if identity else test.broken_length
                length = len(body) + 100 if truncated else len(body)
                self.send_header('Content-Length', str(length))
                self.end_headers()
                self.wfile.write(body)

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
        self.request = Request('GET', f'http://127.0.0.1:{server.server_port}/csw')

    def test_wrong_compressed_length_retries_without_compression(self):
        self.request.headers = {'X-Test': 'preserved'}
        original_session_headers = dict(self.client.session.headers)
        response = self.client.send_request(self.request, timeout=2)
        self.assertEqual(HarvestingJob().get_total_records(response), 6952)
        self.assertEqual(len(self.encodings), 2)
        self.assertIn('gzip', self.encodings[0])
        self.assertEqual(self.encodings[1], 'identity')
        self.assertEqual(response.request.headers['X-Test'], 'preserved')
        self.assertEqual(self.request.headers, {'X-Test': 'preserved'})
        self.assertEqual(dict(self.client.session.headers), original_session_headers)

    def test_invalid_gzip_retries_without_compression(self):
        self.corrupt_gzip = True
        response = self.client.send_request(self.request, timeout=2)
        self.assertEqual(response.content, self.fallback_body)
        self.assertEqual(len(self.encodings), 2)

    def test_valid_compressed_response_is_not_retried(self):
        self.broken_length = False
        response = self.client.send_request(self.request, timeout=2)
        self.assertEqual(response.content, self.fallback_body)
        self.assertEqual(len(self.encodings), 1)

    def test_post_is_not_replayed(self):
        self.request.method = 'POST'
        with patch.object(self.client.session, 'send', side_effect=ChunkedEncodingError('broken')) as send:
            with self.assertRaises(ChunkedEncodingError):
                self.client.send_request(self.request, timeout=2)
        send.assert_called_once()

    def test_truncated_identity_response_still_fails_after_one_fallback(self):
        self.truncate_fallback = True
        with self.assertRaises(ChunkedEncodingError):
            self.client.send_request(self.request, timeout=2)
        self.assertEqual(len(self.encodings), 2)

    def test_explicit_identity_request_is_not_retried(self):
        self.truncate_fallback = True
        for headers in (self.request.headers, self.client.session.headers):
            with self.subTest(headers=headers):
                headers['accept-encoding'] = 'identity'
                self.encodings.clear()
                with self.assertRaises(ChunkedEncodingError):
                    self.client.send_request(self.request, timeout=2)
                self.assertEqual(self.encodings, ['identity'])
                del headers['accept-encoding']

    def test_fallback_errors_still_reach_harvest_validation(self):
        for body, status_code in ((b'<broken', 200), (b'<ExceptionReport/>', 200), (b'<error/>', 400)):
            with self.subTest(body=body, status=status_code):
                self.fallback_body, self.fallback_status = body, status_code
                response = self.client.send_request(self.request, timeout=2)
                self.assertEqual(response.status_code, status_code)
                with patch.object(HarvestingJob, '_log_response_error') as log:
                    self.assertTrue(HarvestingJob()._check_xml_response(response))
                log.assert_called_once_with(response=response)


class CatalogueServiceClientGetRecordsTest(SimpleTestCase):
    def test_get_records_binds_iso_and_csw_type_name_prefixes(self):
        capabilities = Path(
            settings.BASE_DIR, "tests/django/test_data/capabilities/csw/2.0.2.xml").read_bytes()
        client = CatalogueServiceClient(capabilities)
        for type_name in ("gmd:MD_Metadata", "csw:Record"):
            with self.subTest(type_name=type_name):
                request = client.get_records_request(type_names=type_name)
                params = parse_qs(urlsplit(request.url).query)
                self.assertEqual(params["typeNames"], [type_name])
                self.assertEqual(set(params["NAMESPACE"][0].split(",")), {
                    f"xmlns(gmd={NAMESPACE_LOOKUP['gmd']})",
                    f"xmlns(csw={NAMESPACE_LOOKUP['csw_2_0_2']})",
                })


class CatalogueServiceClientAdvertisedMaxRecordsTest(SimpleTestCase):
    """the maxRecords limit of the GetRecords constraints is a hint which harvesting reads
    before it asks the service itself (#694)"""

    def make_client(self, constraints):
        capabilities = f"""
            <Capabilities version="2.0.2" xmlns="http://www.opengis.net/cat/csw/2.0.2"
                xmlns:ows="http://www.opengis.net/ows/1.1">
                <ows:OperationsMetadata><ows:Operation name="GetRecords">
                    {constraints}
                </ows:Operation></ows:OperationsMetadata>
            </Capabilities>
        """.encode()
        return CatalogueServiceClient(capabilities)

    def test_named_max_records_constraint_is_answered(self):
        client = self.make_client(
            '<ows:Constraint name="MaxRecords"><ows:Value>100</ows:Value></ows:Constraint>')
        self.assertEqual(client.advertised_max_records(), 100)

    def test_spelling_with_namespace_prefix_is_found(self):
        client = self.make_client(
            '<ows:Constraint name="csw:maxRecords"><ows:Value>25</ows:Value></ows:Constraint>')
        self.assertEqual(client.advertised_max_records(), 25)

    def test_service_without_the_constraint_answers_none(self):
        client = self.make_client(
            '<ows:Constraint name="SupportedISOQueryables">'
            '<ows:Value>apiso:Abstract</ows:Value></ows:Constraint>')
        self.assertIsNone(client.advertised_max_records())

    def test_non_numeric_value_is_no_limit(self):
        client = self.make_client(
            '<ows:Constraint name="MaxRecords"><ows:Value>unbounded</ows:Value></ows:Constraint>')
        self.assertIsNone(client.advertised_max_records())

    def test_limit_of_another_operation_is_not_the_get_records_limit(self):
        client = CatalogueServiceClient("""
            <Capabilities version="2.0.2" xmlns="http://www.opengis.net/cat/csw/2.0.2"
                xmlns:ows="http://www.opengis.net/ows/1.1">
                <ows:OperationsMetadata>
                    <ows:Operation name="GetRecords"></ows:Operation>
                    <ows:Operation name="GetCapabilities">
                        <ows:Constraint name="MaxRecords"><ows:Value>10</ows:Value></ows:Constraint>
                    </ows:Operation>
                </ows:OperationsMetadata>
            </Capabilities>
        """.encode())
        self.assertIsNone(client.advertised_max_records())
