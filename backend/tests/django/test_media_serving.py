"""HTTP verb restriction of the media fallback view (#782, SonarCloud S3752).

Outside DEBUG the urlconf serves uploaded media through ``protected_serve``, so
that the application can answer media requests on its own. Media is static
content: only the two read verbs may reach the file server, every other verb
must be answered 405 at the url layer.

The route binds ``document_root`` to ``settings.MEDIA_ROOT`` while the urlconf
is imported, so an ``override_settings(MEDIA_ROOT=...)`` never reaches the
view. The 200 case therefore writes into the configured media root, the same
directory a deployment serves.
"""

import uuid
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class ProtectedServeVerbTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media_name = f'protected-serve-{uuid.uuid4()}.png'
        cls.media_path = Path(settings.MEDIA_ROOT) / cls.media_name
        cls.media_path.write_bytes(b'\x89PNG\r\n\x1a\n protected serve')

    @classmethod
    def tearDownClass(cls):
        cls.media_path.unlink(missing_ok=True)
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
