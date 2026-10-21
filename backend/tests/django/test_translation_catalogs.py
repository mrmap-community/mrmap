from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / '.bash_scripts' / 'check_translation_catalogs.sh'
CATALOG = '''msgid ""
msgstr ""
"Project-Id-Version: MrMap\\n"
"POT-Creation-Date: 2026-10-20 10:00+0000\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Report-Msgid-Bugs-To: maintainers@example.com\\n"
"PO-Revision-Date: 2026-10-20 09:00+0000\\n"

#: registry/models/mapcontext.py:100
msgid "title"
msgstr "Titel"

#: registry/models/mapcontext.py:110
msgid "description"
msgstr "Beschreibung"
'''


class TranslationCatalogChecks(unittest.TestCase):
    def compare(self, original, extracted):
        with tempfile.TemporaryDirectory() as directory:
            original_path = Path(directory) / 'original.po'
            extracted_path = Path(directory) / 'extracted.po'
            original_path.write_text(original)
            extracted_path.write_text(extracted)
            return subprocess.run(
                ['/bin/sh', str(SCRIPT), str(original_path), str(extracted_path)],
                capture_output=True, text=True)

    def test_ignores_timestamp_locations_and_wrapping(self):
        extracted = CATALOG.replace('2026-10-20 10:00+0000', '2026-10-21 12:00+0200')
        extracted = extracted.replace('mapcontext.py:100', 'mapcontext.py:150')
        extracted = extracted.replace('msgstr "Beschreibung"', 'msgstr ""\n"Beschrei"\n"bung"')
        result = self.compare(CATALOG, extracted)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_ignores_message_order(self):
        header, title, description = CATALOG.strip().split('\n\n')
        result = self.compare(CATALOG, '\n\n'.join([header, description, title]) + '\n')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_detects_changed_message_beyond_the_old_325_byte_prefix(self):
        self.assertGreater(CATALOG.index('msgid "description"'), 325)
        result = self.compare(CATALOG, CATALOG.replace('msgid "description"', 'msgid "new description"'))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('new description', result.stdout)

    def test_detects_changed_translation(self):
        result = self.compare(CATALOG, CATALOG.replace('msgstr "Titel"', 'msgstr "Name"'))
        self.assertNotEqual(result.returncode, 0)

    def test_detects_fuzzy_translation(self):
        result = self.compare(CATALOG, CATALOG.replace('msgid "title"', '#, fuzzy\nmsgid "title"'))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('fuzzy', result.stdout)

    def test_detects_added_or_removed_message(self):
        removed = CATALOG[:CATALOG.index('#: registry/models/mapcontext.py:110')]
        self.assertNotEqual(self.compare(CATALOG, removed).returncode, 0)
        self.assertNotEqual(self.compare(removed, CATALOG).returncode, 0)

    def test_rejects_malformed_catalog(self):
        result = self.compare(CATALOG, 'not a PO catalog')
        self.assertNotEqual(result.returncode, 0)
