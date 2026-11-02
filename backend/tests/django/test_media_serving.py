"""HTTP verb restriction of the media fallback view (#782, SonarCloud S3752) and the
dumps which it never serves (#888).

Outside DEBUG the urlconf serves uploaded media through ``protected_serve``, so
that the application can answer media requests on its own. Media is static
content: only the two read verbs may reach the file server, every other verb
must be answered 405 at the url layer.

The dumps which the syslog formatter writes into the logs directory of the media
root are the exception: they carry complete sql statements and internal host names
and only the syslog line points at them, so the media route answers them like an
unknown file.

The route binds ``document_root`` to ``settings.MEDIA_ROOT`` while the urlconf
is imported, so an ``override_settings(MEDIA_ROOT=...)`` never reaches the
view. The 200 case therefore writes into the configured media root, the same
directory a deployment serves - and so does every test of the dumps.
"""

import uuid
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from system.logging.formatter import SLOW_REQUEST_DUMP_SUBDIR


class ProtectedServeVerbTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media_name = f'protected-serve-{uuid.uuid4()}.png'
        cls.media_path = Path(settings.MEDIA_ROOT) / cls.media_name
        cls.media_path.write_bytes(b'\x89PNG\r\n\x1a\n protected serve')

        # a dump as the rfc5424 formatter writes it: the sweep of system.tasks
        # takes it back, the test below does not wait for that
        cls.dump_directory = Path(settings.MEDIA_ROOT) / SLOW_REQUEST_DUMP_SUBDIR
        cls.created_dump_directory = not cls.dump_directory.exists()
        cls.dump_directory.mkdir(exist_ok=True)
        cls.dump_name = f'{uuid.uuid4()}.json'
        cls.dump_path = cls.dump_directory / cls.dump_name
        cls.dump_path.write_text('{"metaSDID@request": {"path": "x"}}')

        # the security proxy keeps request and response bodies below a logs
        # directory of its own, inside the media root, and those are media
        cls.proxy_directory = (Path(settings.MEDIA_ROOT) / 'security_proxy'
                               / 'logs' / 'requests')
        cls.created_proxy_directory = not cls.proxy_directory.exists()
        cls.proxy_name = f'{uuid.uuid4()}.json'
        cls.proxy_path = cls.proxy_directory / cls.proxy_name
        cls.proxy_directory.mkdir(parents=True, exist_ok=True)
        cls.proxy_path.write_text('{}')

    @classmethod
    def tearDownClass(cls):
        cls.media_path.unlink(missing_ok=True)
        cls.dump_path.unlink(missing_ok=True)
        cls.proxy_path.unlink(missing_ok=True)
        # only the directories this class created: the checkout may hold dumps of its
        # own, which belong to whoever wrote them
        if cls.created_dump_directory:
            cls.dump_directory.rmdir()
        if cls.created_proxy_directory:
            cls.proxy_directory.rmdir()
        super().tearDownClass()

    def test_get_serves_the_file(self):
        response = self.client.get(f'/media/{self.media_name}')
        self.assertEqual(response.status_code, 200)

    def test_head_serves_the_file(self):
        response = self.client.head(f'/media/{self.media_name}')
        self.assertEqual(response.status_code, 200)

    def test_unknown_file_is_not_found(self):
        response = self.client.get('/media/does/not/exist.png')
        self.assertEqual(response.status_code, 404)

    def test_write_verbs_are_rejected_before_the_file_server(self):
        for verb in ('post', 'put', 'patch', 'delete'):
            response = getattr(self.client, verb)(f'/media/{self.media_name}')
            self.assertEqual(response.status_code, 405, verb)

    def test_a_slow_request_dump_is_not_served(self):
        """The media route answers the dump of a slow request like an unknown file."""
        self.assertTrue(self.dump_path.exists())
        response = self.client.get(
            f'/media/{SLOW_REQUEST_DUMP_SUBDIR}/{self.dump_name}')
        self.assertEqual(response.status_code, 404)

    def test_the_media_next_to_the_logs_directory_is_still_served(self):
        """The refusal asks the dumps of the media root and nothing else.

        The security proxy keeps the bodies it logged below a logs directory of its
        own and those belong to the rows of its request log, which answer them.
        """
        response = self.client.get(
            f'/media/security_proxy/logs/requests/{self.proxy_name}')
        self.assertEqual(response.status_code, 200)

    def test_a_dump_is_not_served_under_any_spelling_of_its_path(self):
        """The path is compared resolved, so no spelling of it answers a dump."""
        for spelling in (
                f'/media/{SLOW_REQUEST_DUMP_SUBDIR}/./{self.dump_name}',
                f'/media/{SLOW_REQUEST_DUMP_SUBDIR}/../{SLOW_REQUEST_DUMP_SUBDIR}'
                f'/{self.dump_name}',
                f'/media/./{SLOW_REQUEST_DUMP_SUBDIR}/{self.dump_name}'):
            response = self.client.get(spelling)
            self.assertEqual(response.status_code, 404, spelling)

    def test_a_write_verb_on_a_dump_answers_like_on_an_unknown_file(self):
        """The dump is refused with the answer every other media path gives.

        The two read verbs answer a dump and an unknown file alike with 404, the
        write verbs with the 405 the media route tells all its paths. An answer
        which differed for the dumps is what would tell a caller that the path of a
        dump is guarded, so the refusal accepts the verbs a media file is asked with
        and nothing else (#888).
        """
        for verb in ('get', 'head', 'post', 'put', 'patch', 'delete'):
            dump = getattr(self.client, verb)(
                f'/media/{SLOW_REQUEST_DUMP_SUBDIR}/{self.dump_name}')
            unknown = getattr(self.client, verb)('/media/does/not/exist.png')
            self.assertEqual(dump.status_code, unknown.status_code, verb)
