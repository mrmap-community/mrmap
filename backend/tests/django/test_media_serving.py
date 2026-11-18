"""HTTP verb restriction of the media fallback view (#782, SonarCloud S3752), the
dumps which it never serves (#888) and the private media prefixes beside them
which it refuses the same way (#1447).

The urlconf serves uploaded media through ``ProtectedServeView``, so
that the application can answer media requests on its own. Media is static
content: only the two read verbs may reach the file server, every other verb
must be answered 405 at the url layer.

Not every file below the media root is media the route serves. The dumps the
syslog formatter writes carry complete sql statements and internal host names
and only the syslog line points at them; the Fernet key files of the external
service authentications, the request and response bodies the security proxy
logged and the metadata documents a harvesting run stages are read on the
filesystem, if at all, and have no HTTP consumer (#1447). The media route
answers every one of those paths like an unknown file, and so does the nginx
of the frontend in front of it (their rows of ``scripts/nginx_routing_smoke.py``).
Everything else - preview images, stored XML documents - is public media and
stays served.

The route binds ``document_root`` to ``settings.MEDIA_ROOT`` while the urlconf
is imported, so an ``override_settings(MEDIA_ROOT=...)`` never reaches the
view. The 200 case therefore writes into the configured media root, the same
directory a deployment serves - and so does every test of the guarded paths.
"""

import contextlib
import importlib.util
import uuid
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from system.logging.formatter import SLOW_REQUEST_DUMP_SUBDIR
from system.views import MEDIA_PRIVATE_SUBPATHS

#: One file below every private prefix, keyed by the url path below /media/.
#: The values are the relative paths the requests ask; a fresh name per run
#: keeps parallel runners and repeated runs out of each other's way.
PRIVATE_MEDIA_FILES = {
    f"{SLOW_REQUEST_DUMP_SUBDIR}": "a-dump.json",
    "ext_auth_keys/7": "service.key",
    "security_proxy/logs/requests": "request-body.json",
    "security_proxy/logs/responses": "response-body.json",
    "temporary_md_metadata_file": "staged-record.xml",
}

#: A stored XML document: private-looking by name, public media by policy -
#: the download links of the frontend open exactly this mount.
PUBLIC_MEDIA_SUBPATH = "xml_documents/4"


class ProtectedServeVerbTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media_name = f'protected-serve-{uuid.uuid4()}.png'
        cls.media_path = Path(settings.MEDIA_ROOT) / cls.media_name
        cls.media_path.write_bytes(b'\x89PNG\r\n\x1a\n protected serve')

        # one file below every private prefix, as its writer lays it out;
        # the sweep of system.tasks and the cleanup command take them back,
        # the tests below do not wait for that
        cls.private_paths = {}
        cls.private_directories = []
        for subpath, filename in PRIVATE_MEDIA_FILES.items():
            directory = Path(settings.MEDIA_ROOT) / subpath
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f'{uuid.uuid4()}-{filename}'
            path.write_text('{"private": "payload"}')
            cls.private_paths[subpath] = path
            cls.private_directories.append(directory)

        # and one stored XML document, which the policy must leave alone
        public_directory = Path(settings.MEDIA_ROOT) / PUBLIC_MEDIA_SUBPATH
        public_directory.mkdir(parents=True, exist_ok=True)
        cls.public_path = public_directory / f'{uuid.uuid4()}-record.xml'
        cls.public_path.write_text('<record/>')
        cls.public_directories = [public_directory]

    @classmethod
    def tearDownClass(cls):
        cls.media_path.unlink(missing_ok=True)
        cls.public_path.unlink(missing_ok=True)
        for path in cls.private_paths.values():
            path.unlink(missing_ok=True)
        # the directory goes with the last file below it, whatever class wrote
        # that file: the parallel runner runs the development subclass below in
        # another process, so both classes share these directories and an
        # rmdir can meet a file of the sibling still running there. A file is
        # what keeps a directory, so the private media a checkout holds of its
        # own belong to whoever wrote them and the rmdir simply does not apply.
        for directory in [*cls.private_directories, *cls.public_directories]:
            while directory != Path(settings.MEDIA_ROOT):
                with contextlib.suppress(OSError):
                    directory.rmdir()
                directory = directory.parent
        super().tearDownClass()

    def test_get_serves_the_file(self):
        response = self.client.get(f'/media/{self.media_name}')
        self.addCleanup(response.close)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content),
                         self.media_path.read_bytes())

    def test_head_serves_the_file(self):
        response = self.client.head(f'/media/{self.media_name}')
        self.addCleanup(response.close)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), b'')
        self.assertEqual(int(response['Content-Length']),
                         self.media_path.stat().st_size)

    def test_unknown_file_is_not_found(self):
        response = self.client.get('/media/does/not/exist.png')
        self.assertEqual(response.status_code, 404)

    def test_unsupported_verbs_are_rejected_before_the_file_server(self):
        for verb in ('post', 'put', 'patch', 'delete', 'options', 'trace'):
            response = getattr(self.client, verb)(f'/media/{self.media_name}')
            self.assertEqual(response.status_code, 405, verb)
            self.assertEqual(response['Allow'], 'GET, HEAD', verb)

    def test_a_slow_request_dump_is_not_served(self):
        """The media route answers the dump of a slow request like an unknown file."""
        dump = self.private_paths[SLOW_REQUEST_DUMP_SUBDIR]
        self.assertTrue(dump.exists())
        response = self.client.get(
            f'/media/{SLOW_REQUEST_DUMP_SUBDIR}/{dump.name}')
        self.assertEqual(response.status_code, 404)

    def test_every_private_prefix_is_not_served(self):
        """#1447: keys, logged bodies and staged harvesting documents refused.

        Every entry of the policy is asked with a real file below it, so a
        prefix the policy names but the route forgets fails here.
        """
        # every policy prefix has a real file below it, and every file of the
        # tests sits below one named prefix - the two sets can never drift
        self.assertTrue(
            all(any(subpath == prefix or subpath.startswith(prefix + "/")
                    for prefix in MEDIA_PRIVATE_SUBPATHS)
                for subpath in PRIVATE_MEDIA_FILES),
            'the tests lay files below a prefix the policy does not guard')
        self.assertEqual(
            {prefix for prefix in MEDIA_PRIVATE_SUBPATHS
             if any(subpath == prefix or subpath.startswith(prefix + "/")
                    for subpath in PRIVATE_MEDIA_FILES)},
            set(MEDIA_PRIVATE_SUBPATHS),
            'a prefix the policy guards has no file of the tests below it')
        for subpath, path in self.private_paths.items():
            response = self.client.get(f'/media/{subpath}/{path.name}')
            self.assertEqual(response.status_code, 404, subpath)

    def test_the_media_next_to_the_private_prefixes_is_still_served(self):
        """The refusal asks the private subpaths and nothing else.

        The stored XML documents of this mount are the download targets of the
        frontend, and a plain media file next to the guarded directories was
        the assertion this test carried before #1447 moved the security proxy
        bodies it named into the refused set: the policy is a prefix list, and
        what the list does not name must keep answering.
        """
        response = self.client.get(
            f'/media/{PUBLIC_MEDIA_SUBPATH}/{self.public_path.name}')
        self.addCleanup(response.close)
        self.assertEqual(response.status_code, 200)

    def test_a_private_file_is_not_served_under_any_spelling_of_its_path(self):
        """The path is compared resolved, so no spelling of it answers."""
        for subpath, path in self.private_paths.items():
            for spelling in (
                    f'/media/{subpath}/./{path.name}',
                    f'/media/{subpath}/../{subpath}/{path.name}',
                    f'/media/./{subpath}/{path.name}'):
                response = self.client.get(spelling)
                self.assertEqual(response.status_code, 404, spelling)

    def test_a_symlink_into_the_guarded_media_is_not_served(self):
        """The route resolves, so a link is judged by its target, not its name."""
        for subpath, target in self.private_paths.items():
            media_link = Path(settings.MEDIA_ROOT) / f'{uuid.uuid4()}.json'
            media_link.symlink_to(target)
            self.addCleanup(media_link.unlink)
            response = self.client.get(f'/media/{media_link.name}')
            self.assertEqual(response.status_code, 404, subpath)

    def test_a_private_file_answers_like_an_unknown_file_for_every_verb(self):
        """The refusal is answered with the answer every other media path gives.

        The two read verbs answer a guarded file and an unknown file alike with
        404, the write verbs with the 405 the media route tells all its paths.
        An answer which differed for the guarded paths is what would tell a
        caller that a path is guarded, so the refusal accepts the verbs a media
        file is asked with and nothing else (#888, #1447).
        """
        for subpath, path in self.private_paths.items():
            for verb in ('get', 'head', 'post', 'put', 'patch', 'delete',
                         'options', 'trace'):
                guarded = getattr(self.client, verb)(
                    f'/media/{subpath}/{path.name}')
                unknown = getattr(self.client, verb)('/media/does/not/exist.png')
                self.assertEqual(guarded.status_code, unknown.status_code,
                                 f'{verb} {subpath}')
                self.assertEqual(guarded.get('Allow'), unknown.get('Allow'),
                                 f'{verb} {subpath}')


@override_settings(DEBUG=True, TESTING=False)
class DevelopmentProtectedServeVerbTests(ProtectedServeVerbTests):
    """Exercise the same media contract through the development URLconf branch.

    The toolbar is no installed app of a test run, which the urlconf asks rather
    than its own DEBUG, so this branch is imported for its media route alone.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Execute a fresh URLconf without replacing the module other tests use.
        spec = importlib.util.find_spec('MrMap.urls')
        urlconf = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(urlconf)
        urlconf_settings = override_settings(ROOT_URLCONF=urlconf)
        urlconf_settings.enable()
        cls.addClassCleanup(urlconf_settings.disable)
