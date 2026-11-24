"""The XML parser policy of #1468, asserted through the imported factory.

``registry/helper/xml.py`` is the only place of the backend which opens an lxml
parser, so the behaviour every untrusted XML entry point relies on - an entity
declaration stays unexpanded and no declared system literal is fetched - is
asserted here rather than once per call site. The offline canary
``scripts/test_xml_parse_guard.py`` checks the same option set on a host without
Django; this module covers what needs the imported module: the function
contracts and the refusal to be softened at a call site. The serialization
caveat of the module docstring is pinned where the rule against it lives, in
``scripts/test_xml_parse_guard.py``.

The negative controls matter more than the assertions themselves: a hardened
parse which answers no file content proves nothing on a machine where the entity
never resolved anyway. Each canary is therefore parsed twice, once with the
option pair measured to leak on the pinned lxml (6.1.3 / libxml2 2.14.6) and
once through the policy.
"""
import tempfile
from pathlib import Path

from django.test import SimpleTestCase
from lxml import etree
from registry.helper import xml as xml_policy

#: what the XXE canary reads if a parser resolves the declaration
CANARY_MARKER = "XXE-CANARY-CONTENT"
#: what a self-declared entity repeats when it is expanded
EXPANSION_MARKER = "expanded"

XXE_DOCUMENT = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE root [ <!ENTITY xxe SYSTEM "%s"> ]>
<root>&xxe;</root>
"""


def _xxe(system_literal: str) -> bytes:
    """The XXE canary as bytes: the document declares an encoding, so it is not
    something a ``str`` may carry through the policy (#1468 refuses that)."""
    return (XXE_DOCUMENT % system_literal).encode("utf-8")


#: seven levels of three, which is 3**7 = 2.187 self-references of the marker
#: once the innermost declaration expands
BOMB_DOCUMENT = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE root [
<!ENTITY a "&b;&b;&b;">
<!ENTITY b "&c;&c;&c;">
<!ENTITY c "&d;&d;&d;">
<!ENTITY d "&e;&e;&e;">
<!ENTITY e "&f;&f;&f;">
<!ENTITY f "&g;&g;&g;">
<!ENTITY g "%s">
]>
<root>&a;</root>
""" % EXPANSION_MARKER

#: the option pair which really reads the file on the pinned lxml: lxml's own
#: defaults keep load_dtd off, so they refuse the declaration instead
LEAKING_PARSER = dict(load_dtd=True, resolve_entities=True)


def _xml(element) -> str:
    """The XML serialization, which is what the backend reads and stores."""
    return etree.tostring(element, encoding="unicode")


class HardenedParseTest(SimpleTestCase):
    """What :func:`parse_untrusted` refuses for a document it did not write."""

    def test_a_system_entity_never_reaches_the_tree_or_its_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            secret = Path(tmp) / "canary-secret.txt"
            secret.write_text(CANARY_MARKER, encoding="utf-8")
            document = _xxe(secret.as_uri())

            leaking = _xml(etree.fromstring(document, parser=etree.XMLParser(
                **LEAKING_PARSER)))
            self.assertIn(CANARY_MARKER, leaking,
                          "the canary did not read the file, so the assertion "
                          "below proves nothing")

            root = xml_policy.parse_untrusted(document)
            self.assertEqual(root.tag, "root")
            for surface in (_xml(root), "".join(root.itertext()),
                            [element.text for element in root]):
                self.assertNotIn(CANARY_MARKER, surface, str(surface)[:200])

    def test_a_self_expanding_declaration_stays_unexpanded(self):
        expanded = _xml(etree.fromstring(
            BOMB_DOCUMENT.encode("utf-8"), parser=etree.XMLParser()))
        self.assertGreater(expanded.count(EXPANSION_MARKER), 100,
                           "the canary did not expand, so the assertion below "
                           "proves nothing")

        root = xml_policy.parse_untrusted(BOMB_DOCUMENT.encode("utf-8"))
        self.assertNotIn(EXPANSION_MARKER, _xml(root))
        self.assertNotIn(EXPANSION_MARKER, "".join(root.itertext()))

    def test_a_document_is_answered_as_a_document_without_opening_the_path(self):
        """The document variant reads the bytes itself, so lxml never sees a path."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "harvested.xml"
            secret = Path(tmp) / "canary-secret.txt"
            secret.write_text(CANARY_MARKER, encoding="utf-8")
            path.write_bytes(_xxe(secret.as_uri()))

            document = xml_policy.parse_untrusted_document(path)
            self.assertEqual(document.getroot().tag, "root")
            self.assertNotIn(CANARY_MARKER, _xml(document.getroot()))
            self.assertNotIn(
                CANARY_MARKER,
                _xml(xml_policy.parse_untrusted_document(
                    path.read_bytes()).getroot()))

    def test_a_call_site_can_not_soften_the_policy(self):
        for option in xml_policy.HARDENED_OPTIONS:
            with self.subTest(option=option), self.assertRaises(ValueError):
                xml_policy.parse_untrusted(b"<root/>", **{option: True})
            with self.subTest(document=option), self.assertRaises(ValueError):
                xml_policy.parse_untrusted_document(b"<root/>", **{option: True})

    def test_an_existing_parser_and_the_options_of_a_call_are_exclusive(self):
        with self.assertRaises(ValueError):
            xml_policy.parse_untrusted(b"<root/>",
                                       parser=xml_policy.hardened_parser(),
                                       huge_tree=True)

    def test_a_hardened_parser_keeps_the_policy_after_the_callers_options(self):
        parser = xml_policy.hardened_parser(resolve_entities=True, no_network=False)
        with tempfile.TemporaryDirectory() as tmp:
            secret = Path(tmp) / "canary-secret.txt"
            secret.write_text(CANARY_MARKER, encoding="utf-8")
            root = xml_policy.parse_untrusted(_xxe(secret.as_uri()), parser=parser)
            self.assertNotIn(CANARY_MARKER, _xml(root))

    def test_nothing_without_a_root_element_is_answered_as_a_root(self):
        for content in (b"", b"   ", b"<!-- no root -->"):
            with self.subTest(content=content), self.assertRaises(etree.XMLSyntaxError):
                xml_policy.parse_untrusted(content)


class ContentReadingTest(SimpleTestCase):
    """:func:`as_bytes` is what keeps a relative system literal resolvable nowhere."""

    def test_every_document_shape_reaches_lxml_as_bytes(self):
        document = b'<?xml version="1.0" encoding="UTF-8"?><root><a/></root>'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "document.xml"
            path.write_bytes(document)
            # a fresh shape per call: a file object answers its bytes only once
            for name, shape in (("bytes", lambda: document),
                                ("path", lambda: path),
                                ("file", lambda: open(path, "rb"))):
                with self.subTest(content=name):
                    self.assertEqual(xml_policy.parse_untrusted(shape()).tag, "root")
                    self.assertEqual(
                        xml_policy.parse_untrusted_document(
                            shape()).getroot().tag, "root")

    def test_a_relative_system_literal_is_not_resolved_from_a_files_directory(self):
        """The point of taking the bytes here: lxml never learns the directory.

        Measured on the pinned lxml: a document handed to lxml as a *path* lets
        a relative SYSTEM literal read a sibling of that file, because libxml2
        resolves the literal against the file's directory. Read the bytes here
        and the literal has no base directory to resolve against.
        """
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "sibling.txt").write_text(CANARY_MARKER, encoding="utf-8")
            document = ('<?xml version="1.0"?>\n'
                        '<!DOCTYPE root [ <!ENTITY xxe SYSTEM "sibling.txt"> ]>\n'
                        '<root>&xxe;</root>\n')
            stored = directory / "harvested.xml"
            stored.write_text(document, encoding="utf-8")

            leak = etree.tostring(
                etree.parse(str(stored), parser=etree.XMLParser(**LEAKING_PARSER)),
                encoding="unicode")
            self.assertIn(CANARY_MARKER, leak,
                          "the path-based control did not read the sibling, so "
                          "the assertion below proves nothing")

            for content in (stored, document):
                with self.subTest(content=type(content).__name__):
                    self.assertNotIn(
                        CANARY_MARKER,
                        _xml(etree.fromstring(xml_policy.as_bytes(content),
                                              parser=etree.XMLParser(**LEAKING_PARSER))))
                    self.assertNotIn(
                        CANARY_MARKER,
                        _xml(xml_policy.parse_untrusted(content)))

    def test_a_str_with_an_encoding_declaration_stays_a_value_error(self):
        with self.assertRaises(ValueError):
            xml_policy.parse_untrusted(
                '<?xml version="1.0" encoding="UTF-8"?><root/>')

    def test_something_which_is_no_document_is_named(self):
        with self.assertRaises(TypeError):
            xml_policy.as_bytes(object())


class TrustedParseTest(SimpleTestCase):
    """:func:`parse_trusted` opens lxml's defaults for a document of this deployment."""

    def test_a_document_of_this_deployment_parses_with_the_lxml_defaults(self):
        self.assertEqual(xml_policy.parse_trusted(
            b"<registry><a>x</a></registry>").findtext("a"), "x")

    def test_a_broken_backup_still_raises(self):
        with self.assertRaises(etree.XMLSyntaxError):
            xml_policy.parse_trusted(b"<unclosed>")


class PolicyModuleIsTheOnlyParserTest(SimpleTestCase):
    """No other backend module builds a parser of its own.

    The static half of this is the host guard of
    ``scripts/xml_parse_guard.py``, which the git hooks and CI run. This is the
    half which needs no tooling: the option set of the policy is exactly the two
    options the issue names, and the module holds the only parser construction
    of its own package.
    """

    def test_the_policy_is_the_two_named_options(self):
        self.assertEqual(xml_policy.HARDENED_OPTIONS,
                         {"resolve_entities": False, "no_network": True})

    def test_the_helpers_module_is_the_only_parser_of_the_package(self):
        helpers = Path(xml_policy.__file__).parent
        builders = sorted(path.name for path in helpers.glob("*.py")
                          if "XMLParser(" in path.read_text(encoding="utf-8")
                          and path.name != "xml.py")
        self.assertEqual(builders, [], f"{builders} build their own parser")
