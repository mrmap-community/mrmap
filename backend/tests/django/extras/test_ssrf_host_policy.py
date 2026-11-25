"""The configurable host allow and deny list of every server-side fetch (#1474, SEC-16).

The address behind a URL is judged at the moment the connection is created, so a name cannot
answer as one address for the check and another for the socket, and every redirect hop is
judged as its own target. A loopback listener is the fetchable endpoint of these tests: a
refused address must never be connected to at all, so the loopback case carries both the
assertion that the policy opens when it is told to and the assertion that it stays closed.
"""
import ipaddress
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from unittest.mock import patch

from django.core.exceptions import ObjectDoesNotExist
from django.test import SimpleTestCase, override_settings
from extras import ssrf
from extras.ssrf import (GuardedHTTPAdapter, GuardedSession, address_is_allowed,
                         host_is_allowed, judge_targets, url_is_fetchable)
from registry.models.metadata import fetch_metadata_document
from registry.models.service import WebMapService
from registry.ows_lib.wms.wms import WebMapServiceClient
from requests import Session
from requests.exceptions import ConnectionError

#: a public address, as the address of a service which is meant to be registered
PUBLIC = '93.184.216.34'


def _literal_of(host):
    """The address a host string spells out, None for a name"""
    try:
        return ipaddress.ip_address((host or '').strip().strip('[]'))
    except ValueError:
        return None


#: the closed default: production, with neither list configured
CLOSED = override_settings(MRMAP_PRODUCTION=True, MRMAP_FETCH_ALLOW_NETWORKS='',
                           MRMAP_FETCH_DENY_NETWORKS='')


@CLOSED
class AddressPolicyTest(SimpleTestCase):
    """the verdict of one address, with the default ranges and with configured entries"""

    def test_public_addresses_are_allowed_by_the_default(self):
        for address in (PUBLIC, '2001:4860:4860::8888'):
            with self.subTest(address=address):
                self.assertTrue(address_is_allowed(ipaddress.ip_address(address)))

    def test_special_use_addresses_are_refused_by_the_default(self):
        refused = ['127.0.0.1', '127.5.5.5', '10.1.2.3', '172.16.5.4', '192.168.1.1',
                   '169.254.169.254', '100.64.0.1', '198.18.0.1', '0.0.0.0', '224.0.0.5',
                   '240.0.0.1', '::1', 'fe80::1', 'fc00::1', 'ff02::1', '2001:db8::1']
        for address in refused:
            with self.subTest(address=address):
                self.assertFalse(address_is_allowed(ipaddress.ip_address(address)), address)

    def test_an_address_embedded_in_ipv6_is_refused_as_the_address_it_carries(self):
        embedded = ['::ffff:127.0.0.1', '::7f00:1', '2002:7f00:1::', '64:ff9b::7f00:1',
                    '::ffff:169.254.169.254', '2002:c0a8:5::']
        for address in embedded:
            with self.subTest(address=address):
                self.assertFalse(address_is_allowed(ipaddress.ip_address(address)), address)

    def test_the_documentation_block_inside_the_teredo_prefix_is_refused(self):
        self.assertFalse(address_is_allowed(ipaddress.ip_address('2001:db8:1234::')))

    def test_an_allow_entry_grants_a_refused_range(self):
        with override_settings(MRMAP_FETCH_ALLOW_NETWORKS='10.20.0.0/16, 2001:0db8:1::/48'):
            self.assertTrue(address_is_allowed(ipaddress.ip_address('10.20.5.6')))
            self.assertTrue(address_is_allowed(ipaddress.ip_address('2001:db8:1::5')))
            self.assertFalse(address_is_allowed(ipaddress.ip_address('10.21.5.6')))

    def test_a_deny_entry_refuses_inside_a_granted_range(self):
        with override_settings(MRMAP_FETCH_ALLOW_NETWORKS='10.0.0.0/8',
                               MRMAP_FETCH_DENY_NETWORKS='10.20.30.40/32'):
            self.assertTrue(address_is_allowed(ipaddress.ip_address('10.1.1.1')))
            self.assertFalse(address_is_allowed(ipaddress.ip_address('10.20.30.40')))

    def test_a_deny_entry_wins_over_the_public_default(self):
        with override_settings(MRMAP_FETCH_DENY_NETWORKS=f'{PUBLIC}/32'):
            self.assertFalse(address_is_allowed(ipaddress.ip_address(PUBLIC)))

    def test_an_allow_entry_wins_over_the_refused_default(self):
        with override_settings(MRMAP_FETCH_ALLOW_NETWORKS='169.254.0.0/16'):
            self.assertTrue(address_is_allowed(ipaddress.ip_address('169.254.1.1')))

    def test_both_lists_understand_the_embedded_spelling_of_an_address(self):
        with override_settings(MRMAP_FETCH_ALLOW_NETWORKS='10.0.0.0/8',
                               MRMAP_FETCH_DENY_NETWORKS='10.20.30.40/32'):
            self.assertFalse(address_is_allowed(ipaddress.ip_address('::ffff:10.20.30.40')))
            self.assertFalse(address_is_allowed(ipaddress.ip_address('64:ff9b::a14:1e28')))
            self.assertTrue(address_is_allowed(ipaddress.ip_address('::ffff:10.1.1.1')))

    def test_a_list_may_be_a_string_or_a_sequence(self):
        entries = ('10.20.0.0/16', '192.168.9.0/24')
        for spelling in (entries, list(entries), '10.20.0.0/16; 192.168.9.0/24'):
            with self.subTest(spelling=spelling):
                with override_settings(MRMAP_FETCH_ALLOW_NETWORKS=spelling):
                    self.assertTrue(address_is_allowed(ipaddress.ip_address('10.20.1.1')))
                    self.assertTrue(address_is_allowed(ipaddress.ip_address('192.168.9.9')))

    def test_an_unparseable_entry_is_ignored_with_a_warning(self):
        with self.assertLogs('extras.ssrf', level='WARNING') as logs:
            with override_settings(MRMAP_FETCH_ALLOW_NETWORKS='not-a-cidr, 10.0.0.0/8'):
                self.assertTrue(address_is_allowed(ipaddress.ip_address('10.9.9.9')))
        self.assertIn('not-a-cidr', '\n'.join(logs.output))

    def test_a_host_name_is_judged_by_its_addresses_and_not_by_its_text(self):
        self.assertTrue(host_is_allowed('internal.example'))
        self.assertTrue(url_is_fetchable('http://internal.example/x'))
        self.assertTrue(url_is_fetchable(f'http://{PUBLIC}/capabilities'))
        self.assertFalse(url_is_fetchable('http://169.254.169.254/latest/meta-data/'))
        self.assertFalse(url_is_fetchable('http://[::ffff:127.0.0.1]/x'))


class DevelopmentAllowanceTest(SimpleTestCase):
    """the ranges a deployment outside production may reach without naming them"""

    def test_the_own_ranges_are_granted_only_outside_production(self):
        for address in ('127.0.0.1', '10.0.0.1', '172.17.0.2', '192.168.1.5'):
            with override_settings(MRMAP_PRODUCTION=False, MRMAP_FETCH_DENY_NETWORKS='',
                                   MRMAP_FETCH_ALLOW_NETWORKS=''):
                self.assertTrue(address_is_allowed(ipaddress.ip_address(address)), address)
            with override_settings(MRMAP_PRODUCTION=True, MRMAP_FETCH_DENY_NETWORKS='',
                                   MRMAP_FETCH_ALLOW_NETWORKS=''):
                self.assertFalse(address_is_allowed(ipaddress.ip_address(address)), address)

    def test_a_deny_entry_refuses_inside_the_development_allowance(self):
        with override_settings(MRMAP_PRODUCTION=False, MRMAP_FETCH_ALLOW_NETWORKS='',
                               MRMAP_FETCH_DENY_NETWORKS='127.0.0.1/32'):
            self.assertFalse(address_is_allowed(ipaddress.ip_address('127.0.0.1')))
            self.assertTrue(address_is_allowed(ipaddress.ip_address('127.0.0.2')))

    def test_an_allow_entry_grants_an_internal_range_in_production(self):
        with override_settings(MRMAP_PRODUCTION=True, MRMAP_FETCH_ALLOW_NETWORKS='10.30.0.0/16',
                               MRMAP_FETCH_DENY_NETWORKS=''):
            self.assertTrue(address_is_allowed(ipaddress.ip_address('10.30.1.1')))

    def test_a_publicly_spelled_address_is_granted_in_production(self):
        with override_settings(MRMAP_PRODUCTION=True, MRMAP_FETCH_ALLOW_NETWORKS='',
                               MRMAP_FETCH_DENY_NETWORKS=''):
            self.assertTrue(url_is_fetchable('https://services.example/wms'))


@CLOSED
class TargetCheckTest(SimpleTestCase):
    """`judge_targets`, the judgment one connection undergoes"""

    def test_an_unresolvable_host_is_refused_rather_than_allowed(self):
        with self.assertRaises(ConnectionError):
            judge_targets('does-not-exist.invalid', 80)

    def test_every_answer_of_a_name_is_judged(self):
        # one public, one internal: the rebinding setup the policy exists for
        answers = [(2, 1, 6, '', (PUBLIC, 80)), (2, 1, 6, '', ('10.1.1.1', 80))]
        with patch('extras.ssrf.socket.getaddrinfo', return_value=answers):
            with self.assertRaises(ConnectionError):
                judge_targets('rebind.example', 80)

    def test_a_name_which_only_answers_publicly_is_judged_through(self):
        # the addresses of the very lookup which was judged are what the caller connects to
        answers = [(2, 1, 6, '', (PUBLIC, 80))]
        with patch('extras.ssrf.socket.getaddrinfo', return_value=answers):
            self.assertEqual(judge_targets('services.example', 80), [PUBLIC])

    def test_a_tunneling_proxy_target_is_judged(self):
        answers = [(2, 1, 6, '', (PUBLIC, 3128))]
        with patch('extras.ssrf.socket.getaddrinfo', side_effect=lambda host, *a: answers
                   if host == 'proxy.example' else [(2, 1, 6, '', ('10.0.0.9', 80))]):
            with self.assertRaises(ConnectionError):
                judge_targets('proxy.example', 3128, tunnel=('internal.example', 80))


class ListeningServerTest(SimpleTestCase):
    """a loopback listener which counts the requests it actually answered"""

    def setUp(self):
        test = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                test.requested.append(self.path)
                body = b'<Ok/>'
                self.send_response(200)
                self.send_header('Content-Type', 'application/xml')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.requested = []
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self._stop, server, thread)
        self.port = server.server_port
        self.origin = f'http://127.0.0.1:{self.port}'

    @staticmethod
    def _stop(server, thread):
        """stop the listener in the one order which cannot deadlock

        ``addCleanup`` runs its entries in reverse order, so joining in a separate entry would
        wait for a thread which the shutdown that frees it only reaches afterwards.
        """
        server.shutdown()
        thread.join(10)
        server.server_close()


class GuardedSessionFetchingTest(ListeningServerTest):
    """a `GuardedSession` never opens a socket towards a refused address"""

    @CLOSED
    def test_a_refused_loopback_is_never_connected_to(self):
        with GuardedSession() as session, self.assertRaises(ConnectionError):
            session.get(f'{self.origin}/capabilities', timeout=5)
        self.assertEqual(self.requested, [])

    @override_settings(MRMAP_PRODUCTION=True, MRMAP_FETCH_ALLOW_NETWORKS='127.0.0.0/8',
                       MRMAP_FETCH_DENY_NETWORKS='')
    def test_an_allow_entry_lets_the_same_address_be_fetched(self):
        with GuardedSession() as session:
            response = session.get(f'{self.origin}/capabilities', timeout=5)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.requested, ['/capabilities'])

    @override_settings(MRMAP_PRODUCTION=True, MRMAP_FETCH_ALLOW_NETWORKS='127.0.0.0/8',
                       MRMAP_FETCH_DENY_NETWORKS='127.0.0.1/32')
    def test_a_deny_entry_refuses_an_address_inside_a_granted_range(self):
        with GuardedSession() as session, self.assertRaises(ConnectionError):
            session.get(f'{self.origin}/capabilities', timeout=5)
        self.assertEqual(self.requested, [])

    @override_settings(MRMAP_PRODUCTION=False, MRMAP_FETCH_ALLOW_NETWORKS='',
                       MRMAP_FETCH_DENY_NETWORKS='')
    def test_a_redirect_hop_is_judged_by_its_own_target(self):
        # the hop to a refused address is refused even when the first URL was granted
        with patch.object(ssrf, 'address_is_allowed',
                          side_effect=lambda address: str(address) != '127.0.0.1'):
            with self.assertRaises(ConnectionError):
                with GuardedSession() as session:
                    session.get(f'{self.origin}/capabilities', timeout=5)

    @override_settings(MRMAP_PRODUCTION=True, MRMAP_FETCH_ALLOW_NETWORKS='127.0.0.0/8',
                       MRMAP_FETCH_DENY_NETWORKS='')
    def test_a_plain_session_of_the_same_process_is_unaffected(self):
        with Session() as session:
            response = session.get(f'{self.origin}/capabilities', timeout=5)
        self.assertEqual(response.status_code, 200)

    @override_settings(MRMAP_PRODUCTION=True, MRMAP_FETCH_ALLOW_NETWORKS='127.0.0.0/8',
                       MRMAP_FETCH_DENY_NETWORKS='127.0.0.2/32')
    def test_a_name_which_answers_differently_to_the_guard_and_the_socket_is_never_connected_to(
            self):
        """the rebinding setup: judged and connected must be the answer of one lookup

        The name answers the granted loopback address to the first lookup and the refused
        decoy address to the next. Whoever resolved the name a second time for the socket
        would reach the decoy, which is what this asserts cannot happen: the decoy is never
        connected to, the judged address answers, and the name is asked exactly once.
        """
        asked = []
        real_getaddrinfo = socket.getaddrinfo

        def resolving(host, port, *args):
            if _literal_of(host) is not None:
                # a literal is resolved by the resolver it would really have
                return real_getaddrinfo(host, port, *args)
            asked.append(host)
            address = '127.0.0.1' if asked.count(host) == 1 else '127.0.0.2'
            return [(socket.AF_INET, 1, 6, '', (address, port))]

        decoy, decoy_hits = self._listener('127.0.0.2', self.port)
        with patch.object(ssrf.socket, 'getaddrinfo', side_effect=resolving):
            with GuardedSession() as session:
                response = session.get(
                    f'http://rebind.example:{self.port}/capabilities', timeout=5)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.requested, ['/capabilities'])
        self.assertEqual(decoy_hits, [],
                         'the refused decoy answered: the socket went where the guard never '
                         'looked')

    @override_settings(MRMAP_PRODUCTION=True, MRMAP_FETCH_ALLOW_NETWORKS='127.0.0.0/8',
                       MRMAP_FETCH_DENY_NETWORKS='')
    def test_a_name_whose_first_answer_times_out_falls_through_to_the_next(self):
        """the fallback `create_connection` gave per answer has to survive the single lookup

        Both answers are granted, so both may be dialed. The first black-holes the handshake
        and the second is the live listener: a guard which resolves the name itself has to
        keep walking the answer instead of giving up on the address which timed out, or a
        multi-homed service whose first record is dead fails probes it used to pass.
        """
        self._blackhole('127.0.0.2')
        answers = [(socket.AF_INET, 1, 6, '', ('127.0.0.2', self.port)),
                   (socket.AF_INET, 1, 6, '', ('127.0.0.1', self.port))]
        with patch.object(ssrf.socket, 'getaddrinfo',
                          side_effect=self._resolve({'multi.example': answers})):
            with GuardedSession() as session:
                response = session.get(
                    f'http://multi.example:{self.port}/capabilities', timeout=1)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.requested, ['/capabilities'])

    @override_settings(MRMAP_PRODUCTION=True, MRMAP_FETCH_ALLOW_NETWORKS='127.0.0.0/8',
                       MRMAP_FETCH_DENY_NETWORKS='')
    def test_a_name_whose_answers_all_fail_is_still_reported_as_unreachable(self):
        # falling through every answer must not turn a dead endpoint into a silent success
        self._blackhole('127.0.0.2')
        self._blackhole('127.0.0.3')
        answers = [(socket.AF_INET, 1, 6, '', ('127.0.0.2', self.port)),
                   (socket.AF_INET, 1, 6, '', ('127.0.0.3', self.port))]
        with patch.object(ssrf.socket, 'getaddrinfo',
                          side_effect=self._resolve({'dead.example': answers})):
            with GuardedSession() as session:
                with self.assertRaises(ConnectionError):
                    session.get(f'http://dead.example:{self.port}/capabilities', timeout=1)
        self.assertEqual(self.requested, [])

    @staticmethod
    def _resolve(by_name):
        """a resolver answering ``by_name`` for names and the real one for literals

        Handing `return_value` to the resolver would answer a *literal* with the address list
        too, and `create_connection` would then walk that list itself: the test would pass no
        matter what the guard does, which is the trap a rebinding test has to avoid.
        """
        real_getaddrinfo = socket.getaddrinfo

        def resolving(host, port, *args):
            if _literal_of(host) is None and host in by_name:
                return by_name[host]
            return real_getaddrinfo(host, port, *args)

        return resolving

    def _blackhole(self, address):
        """a listening socket on ``address`` whose accept queue is full, so connects stall

        An address which is unreachable without refusing answers by dropping the handshake
        rather than by refusing it, and that is the difference a fallback has to tell apart:
        a refused address is a closed port, a dropped one is the timeout this simulates. The
        fill sockets get a timeout of their own so filling costs nothing when they stall.
        """
        listener = socket.socket()
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((address, self.port))
        listener.listen(1)
        # fill the queue so the connect under test is the one which has to wait
        queued = [socket.socket() for _ in range(4)]
        for one in queued:
            one.settimeout(0.05)
            try:
                one.connect((address, self.port))
            except OSError:
                pass

        def release():
            for one in queued:
                one.close()
            listener.close()

        self.addCleanup(release)
        return listener

    def _listener(self, address, port=0):
        """another listener which counts what it answered, stopped with the test

        ``port`` lets a decoy sit on the very port of the fetched service, so a socket which
        re-resolved the name reaches an endpoint which really answers instead of a closed one.
        """
        hits = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                hits.append(self.path)
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain')
                self.send_header('Content-Length', '5')
                self.end_headers()
                self.wfile.write(b'SECRE')

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer((address, port), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self._stop, server, thread)
        return server, hits


@CLOSED
class FetchPathPolicyTest(SimpleTestCase):
    """the fetch paths of the registry ask through a session which carries the policy

    The `auth` of a service is a reverse relation, so reading it on an unsaved instance is a
    database query; `databases` grants it because these tests judge which session a service
    builds, and the lookup of its authentication is part of that path.
    """

    databases = {'default'}

    def test_the_session_of_a_service_is_guarded(self):
        service = WebMapService(id='00000000-0000-0000-0000-000000000000')
        session = service.get_session_for_request()
        self.assertIsInstance(session, GuardedSession)
        self.addCleanup(session.close)

    def test_a_missing_authentication_does_not_stop_the_guarded_session(self):
        service = WebMapService(id='00000000-0000-0000-0000-000000000000')
        with patch.object(type(service), 'auth',
                          new=property(lambda self: (_ for _ in ()).throw(ObjectDoesNotExist()))):
            session = service.get_session_for_request()
        self.assertIsInstance(session, GuardedSession)
        self.addCleanup(session.close)

    def test_the_adapter_of_a_service_session_carries_the_policy(self):
        service = WebMapService(id='00000000-0000-0000-0000-000000000000')
        session = service.get_session_for_request()
        self.addCleanup(session.close)
        for prefix in ('http://', 'https://'):
            with self.subTest(prefix=prefix):
                self.assertIsInstance(session.get_adapter(f'{prefix}example/x'),
                                      GuardedHTTPAdapter)

    def test_an_advertised_metadata_reference_is_fetched_through_the_guard(self):
        with patch('registry.models.metadata.GuardedSession') as guarded:
            with self.assertRaises(Exception):
                # the mocked answer is no document; what is asserted is who opened it
                fetch_metadata_document('http://10.0.0.9/md.xml')
        self.assertTrue(guarded.called)


class ClientSessionTest(SimpleTestCase):
    """the session an `OgcClient` asks through

    A client which only maps an already loaded capabilities document answers without ever
    asking anyone, which is what the serializer of a service list does for every WMS of the
    page. It must not pay for a session and its connection pool, and the client which does
    ask must get a session which carries the policy.
    """

    CAPABILITIES = (
        b'<WMS_Capabilities version="1.3.0" xmlns="http://www.opengis.net/wms"'
        b' xmlns:xlink="http://www.w3.org/1999/xlink">'
        b'<Service><Name>WMS</Name></Service>'
        b'<Capability><Request>'
        b'<GetCapabilities><Format>text/xml</Format><DCPType><HTTP><Get>'
        b'<OnlineResource xlink:href="https://example.test/wms?"/>'
        b'</Get></HTTP></DCPType></GetCapabilities>'
        b'<GetMap><Format>image/png</Format><DCPType><HTTP><Get>'
        b'<OnlineResource xlink:href="https://example.test/wms?"/>'
        b'</Get></HTTP></DCPType></GetMap></Request></Capability></WMS_Capabilities>')

    def test_a_client_which_never_asks_never_builds_a_session(self):
        # patched where it is looked up: core.py holds the name it imports itself
        with patch('registry.ows_lib.client.core.GuardedSession') as guarded:
            client = WebMapServiceClient(self.CAPABILITIES)
            # mapping the document and building a request out of it asks nobody anything -
            # this is the path of the service list serializer (#1774 review)
            self.assertEqual(client.service_type, 'WMS')
            self.assertIn('SERVICE=WMS', client.get_capabilities_request().url)
        guarded.assert_not_called()

    def test_the_session_of_a_client_is_guarded_and_its_own(self):
        first = WebMapServiceClient(self.CAPABILITIES)
        second = WebMapServiceClient(self.CAPABILITIES)
        self.addCleanup(first.session.close)
        self.addCleanup(second.session.close)
        self.assertIsInstance(first.session, GuardedSession)
        self.assertIsNot(first.session, second.session,
                         'two clients share one session and therefore one connection pool')
        for prefix in ('http://', 'https://'):
            with self.subTest(prefix=prefix):
                self.assertIsInstance(first.session.get_adapter(f'{prefix}example/x'),
                                      GuardedHTTPAdapter)

    def test_the_session_of_the_caller_is_the_session_of_the_client(self):
        given = Session()
        client = WebMapServiceClient(self.CAPABILITIES, session=given)
        self.assertIs(client.session, given)


class ConfiguredNetworksTest(SimpleTestCase):
    """`_networks`, the parser of what an operator writes"""

    def test_a_broken_entry_is_dropped_and_a_good_one_kept(self):
        with self.assertLogs('extras.ssrf', level='WARNING'):
            networks = ssrf._networks('10.0.0.0/8, garbage, 2001:db8::/32')
        self.assertEqual(networks, [ipaddress.ip_network('10.0.0.0/8'),
                                    ipaddress.ip_network('2001:db8::/32')])

    def test_a_host_without_a_prefix_is_read_as_one_address(self):
        self.assertEqual(ssrf._networks('10.1.2.3'), [ipaddress.ip_network('10.1.2.3/32')])

    def test_nothing_configured_is_an_empty_list(self):
        self.assertEqual(ssrf._networks(None), [])
        self.assertEqual(ssrf._networks('  , ; '), [])
