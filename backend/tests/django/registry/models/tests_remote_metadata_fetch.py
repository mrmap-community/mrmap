"""What the fetch of a remote metadata document does when a host misbehaves.

The reference of a registration points at an arbitrary third-party host, and
the fetch of its document is the only request of the collection made against
it. #1260 is about what that fetch answers when the host does not cooperate,
so these tests answer the fetch themselves: the document is served by a mocked
transport, and once by a socket which accepts the connection and then never
answers - the case no mock can prove, because a mock which returns says
nothing about the window the request really waits in.

What the tests read is the *kind* of the failure: "the server did not answer",
"the server answered 404" and "that host could not be reached" are different
sentences for the person who has to fix a reference, and they are not equally
worth another attempt - only the transient ones are handed back to celery's
retry (see ``tests/django/registry/tasks/tests_fetch_remote_metadata.py``).
"""

import socket
import threading
import time
from unittest.mock import patch

from django.test import TestCase, tag
from registry.exceptions.metadata import (MetadataFetchTimeout,
                                          MetadataFetchUnreachable)
from registry.exceptions.service import NoContent
from registry.models.metadata import (MetadataContact,
                                      WebMapServiceRemoteMetadata)
from registry.models.service import WebMapService
from registry.settings import REGISTRATION_REQUEST_TIMEOUT_SECONDS
from requests.exceptions import ConnectionError, ReadTimeout
from tests.django.utils import MockResponse

# A window small enough to keep the test quick and still a window the fetch has
# to wait out: the value of the constant itself is asserted separately.
SILENT_SERVER_TIMEOUT = 1.0


@tag("registry", "models")
class RemoteMetadataFetchTest(TestCase):
    """The request a ``RemoteMetadata`` makes, and what each answer becomes."""

    def setUp(self):
        contact = MetadataContact.objects.create(
            name='Fetch test contact')
        self.service = WebMapService.objects.create(
            title='Metadata fetch test service',
            version=130,
            origin=1,
            service_url='http://metadata.example.org/wms',
            metadata_contact=contact,
            service_contact=contact)
        self.remote_metadata = WebMapServiceRemoteMetadata.objects.create(
            describes=self.service,
            link='http://metadata.example.org/record.xml')

    # -- the bound of the request --------------------------------------------

    def test_the_request_is_sent_with_the_shared_timeout(self):
        """The fetch asks the transport for the registration's bound.

        The value is asserted where the request leaves the model: a timeout
        which is computed but never handed over bounds nothing, and the same
        value is what the capabilities request of the very same registration
        waits for (#1260).
        """
        with patch('registry.models.metadata.Session') as session:
            session.return_value.send.return_value = MockResponse(
                status_code=200, content='<metadata/>')
            self.remote_metadata.fetch_remote_content()

        self.assertEqual(
            session.return_value.send.call_args.kwargs['timeout'],
            REGISTRATION_REQUEST_TIMEOUT_SECONDS)

    def test_a_server_which_stays_silent_ends_the_fetch_within_the_timeout(self):
        """A silent host costs one window, not a worker indefinitely.

        The listener accepts and never answers - the defect of #1260 itself.
        The fetch has to end with a named timeout after one window of the
        timeout: a window which is not waited at all would mean the request
        never reached the socket, and several windows would mean the transport
        repeats the silence inside one delivery and keeps a worker of the
        ``download`` queue through every one of them.
        """
        self._a_server_which_never_answers()
        with patch('registry.models.metadata.REGISTRATION_REQUEST_TIMEOUT_SECONDS',
                   SILENT_SERVER_TIMEOUT):
            started = time.monotonic()
            with self.assertRaises(MetadataFetchTimeout) as captured:
                self.remote_metadata.fetch_remote_content(save=False)
        elapsed = time.monotonic() - started

        self.assertGreaterEqual(elapsed, SILENT_SERVER_TIMEOUT * 0.9,
                                "the request did not wait for the answer")
        self.assertLess(elapsed, SILENT_SERVER_TIMEOUT * 3,
                        f"the fetch waited {elapsed}s for a silent server")
        # and what it answers says what the server did not do
        self.assertIn('did not answer within', str(captured.exception))

    def test_a_refused_connection_is_named_apart_from_silence(self):
        """Nothing listened on the other side: that is its own answer.

        Transient like a timeout - it is retried - but named apart, because
        'nothing listens there' and 'it went silent' are fixed by different
        people (#1260).
        """
        with patch('registry.models.metadata.Session') as session:
            session.return_value.send.side_effect = ConnectionError(
                'connection refused')
            with self.assertRaises(MetadataFetchUnreachable) as captured:
                self.remote_metadata.fetch_remote_content(save=False)

        self.assertIn('could not be reached', str(captured.exception))
        # the original sentence of the transport is kept below the named one
        self.assertEqual(str(captured.exception.__cause__),
                         'connection refused')

    # -- an answer is not a timeout ------------------------------------------

    def test_an_answer_of_404_names_the_status_which_was_answered(self):
        """'The server answered 404' is not 'the server did not answer'.

        The status is the whole point for whoever fixes the reference: a link
        which moved reads differently from a host which is down, and neither
        one is fetched by trying again (#1260).
        """
        with patch('registry.models.metadata.Session') as session:
            session.return_value.send.return_value = MockResponse(
                status_code=404, content='')
            with self.assertRaises(NoContent) as captured:
                self.remote_metadata.fetch_remote_content(save=False)

        self.assertIn('404', str(captured.exception))

    def test_an_empty_answer_says_the_server_sent_nothing(self):
        """A 200 without a document is its own sentence, too."""
        with patch('registry.models.metadata.Session') as session:
            session.return_value.send.return_value = MockResponse(
                status_code=200, content='')
            with self.assertRaises(NoContent) as captured:
                self.remote_metadata.fetch_remote_content(save=False)

        self.assertIn('no content', str(captured.exception))

    def test_the_fetch_of_a_silent_host_leaves_the_content_untouched(self):
        """A failed fetch does not store a broken document under the row."""
        self.remote_metadata.remote_content = '<metadata>kept</metadata>'
        self.remote_metadata.save()

        with patch('registry.models.metadata.Session') as session:
            session.return_value.send.side_effect = ReadTimeout('too slow')
            with self.assertRaises(MetadataFetchTimeout):
                self.remote_metadata.fetch_remote_content()

        self.remote_metadata.refresh_from_db()
        self.assertEqual(self.remote_metadata.remote_content,
                         '<metadata>kept</metadata>')

    # -- helpers -----------------------------------------------------------

    def _a_server_which_never_answers(self):
        """A host which accepts the connection and then stays silent.

        The listener keeps every connection it takes open: an answer of any
        kind, even a closed socket, would be an answer, and the point is that
        there is none. The ``accept`` loop times out on a short window rather
        than blocking forever, because closing a socket on Linux does not wake
        a thread already waiting in it - only the flag which the timeout
        re-reads ends the thread.
        """
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(('127.0.0.1', 0))
        listener.settimeout(0.1)
        listener.listen(8)
        port = listener.getsockname()[1]

        accepted = []
        stopped = threading.Event()

        def accept_and_stay_silent():
            while not stopped.is_set():
                try:
                    connection, _ = listener.accept()
                except TimeoutError:
                    continue  # nobody connected: look at the flag again
                except OSError:
                    return  # the listener was closed
                accepted.append(connection)

        thread = threading.Thread(target=accept_and_stay_silent, daemon=True)
        thread.start()

        # run order (cleanups run last added first): set the stop flag, which
        # the accept loop re-reads within its short window, then close the
        # listener, join the thread, and take the connections the thread
        # collected back
        self.addCleanup(lambda: [c.close() for c in accepted])
        self.addCleanup(thread.join)
        self.addCleanup(listener.close)
        self.addCleanup(stopped.set)

        self.remote_metadata.link = f'http://127.0.0.1:{port}/record.xml'
        return self.remote_metadata.link
