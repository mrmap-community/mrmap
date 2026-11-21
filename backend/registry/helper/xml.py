"""The one XML parser policy of the deployment (#1468).

lxml parses with ``resolve_entities=True`` and ``no_network=False`` by default.
A document which declares an internal-subset entity therefore lets whoever
wrote that document read a local file of this deployment and see its content
echoed back, and a declaration which expands itself several times grows
quadratically until the worker is gone. Every XML which does not originate from
this deployment's own writers must parse hardened:

* ``resolve_entities=False`` keeps a declared entity unexpanded, so the text of
  a SYSTEM or PUBLIC entity never enters the tree and appears neither in the
  tree nor in anything serialized from it.
* ``no_network=True`` refuses to fetch a declared system literal at all.

Trusted is not the same as untrusted-but-parsed-hardened. :func:`parse_trusted`
is only for documents this deployment wrote itself: a stored XML backup it made
of its own database, a schema shipped in the package. Its name says that it
opens the parser, so a reviewer sees which sites claim the exception and can
check what writes them.

Site policy: every new read of XML goes through one of these functions, and
``scripts/xml_parse_guard.py`` - the host-side check the git hooks and CI run -
fails the tree for a bare ``etree.fromstring`` or ``etree.parse`` in production
code outside this module.

Nothing else is added to the hardened option set. lxml's own defaults already
refuse to recover into a partial tree (``recover``), refuse an excessively deep
or wide document (``huge_tree``) and refuse to load a DTD (``load_dtd``), and a
document is never handed to lxml as a *path*: the bytes are always read here,
because a relative system literal resolves against the directory of the file
lxml was told to open. A site which genuinely needs one more option asks for it
at its own call, so that opening anything stays visible.

Never keep a parser of this module as a module level object: lxml keeps the
parser which read a document alive as part of that document, so one shared
parser instance grows with every document it ever read and is never collected
while any of them is referenced - the same holding-on that the cache release of
#1415 removed for the parsed XML cache. Each call builds its parser, and a
caller which wants one instance for a family of documents gets it from
:func:`hardened_parser` and owns its lifetime.

Hardened means unexpanded, and that is not the same as unserved by every lxml
function. lxml re-expands a declaration while it serializes a tree as *text*,
which is why no site of the backend reads an untrusted document that way - the
check ``test_no_backend_site_serializes_with_method_text`` of
``scripts/test_xml_parse_guard.py`` refuses the tree for it and demonstrates the
expansion. Read an untrusted document as a tree or as XML and take the text of
the individual elements. What a hardened tree holds is the reference: measured on
lxml 6.1.3 / libxml2 2.14.6, a document declaring
``<!ENTITY xxe SYSTEM "file:///etc/passwd">`` parses to ``<root>&xxe;</root>``,
and the reference stays unexpanded in ``.text``, in ``itertext()`` and in the XML
serialization.
"""
import re
from io import BytesIO
from os import PathLike
from pathlib import Path

from lxml import etree

#: the options every untrusted document is parsed with (#1468)
HARDENED_OPTIONS = {
    "resolve_entities": False,
    "no_network": True,
}

#: the XML declaration of a string which names an encoding, i.e. the input lxml
#: refuses and which this module refuses with the same message
_ENCODING_DECLARATION = re.compile(
    r'^\s*<\?xml[^>]*\bencoding\s*=\s*["\'][^"\']*["\']', re.IGNORECASE)


def hardened_parser(**kwargs) -> etree.XMLParser:
    """A parser which refuses entities and the network.

    A caller may add its own options, but not soften the policy: the hardened
    options are applied after the caller's.
    """
    kwargs.update(HARDENED_OPTIONS)
    return etree.XMLParser(**kwargs)


def as_bytes(content) -> bytes:
    """The bytes of ``content``, which may be bytes, str, a path or a file.

    The bytes are always taken here rather than handed to lxml: a document read
    from a *path* lets lxml resolve a relative system literal of the document
    against that file's directory, which a harvested document uses to read its
    own siblings. Read as bytes, the document has no directory to resolve
    anything against.

    A ``str`` which declares an encoding is refused, which is what lxml does with
    the same input, so a caller gets the same answer from either. Re-encoding it
    under a fixed utf-8 instead - which is what a plain ``str.encode()`` here
    would do - contradicts the declaration the bytes are sent with: measured on
    the pinned lxml, a decoded ``ISO-8859-1`` document whose text is ``ü`` reads
    back as ``Ã¼`` that way, where the bytes the document describes read ``ü``.
    A decoded string carries no encoding to declare, so a document without a
    declaration or one declaring utf-8 still parses; the refusal names the input
    whose bytes can not be known here.
    """
    if hasattr(content, "read"):
        return content.read()
    if isinstance(content, bytes):
        return content
    if isinstance(content, str):
        if _ENCODING_DECLARATION.search(content) is not None:
            raise ValueError(
                "Unicode strings with encoding declaration are not supported. "
                "Please use bytes input or XML fragments without declaration")
        return content.encode("utf-8")
    if isinstance(content, PathLike):
        return Path(content).read_bytes()
    raise TypeError(
        f"can not read an XML document from {type(content).__name__}")


def parse_untrusted(content, *, parser=None, **parser_kwargs) -> etree._Element:
    """The root of a document which an external side wrote.

    An entity the document declares stays unexpanded and no declared system
    literal is fetched, so the tree carries neither the content of a local file
    nor a remote one, no matter what the document declares. Anything which is
    not a well-formed document with a root element raises
    :class:`lxml.etree.XMLSyntaxError`, empty and whitespace-only input
    included - lxml answers no root for those.

    :param content: ``bytes``, ``str``, a path or a readable file object. A
        ``str`` which declares an encoding raises :class:`ValueError` the way
        lxml does, because the declaration contradicts an already decoded
        string; read such a document as bytes.
    :param parser: an existing parser, e.g. from :func:`hardened_parser`, to
        read several documents with one instance without softening the policy
    :param parser_kwargs: further options for the parser of this call. They can
        not accompany ``parser``, and they can not repeat a hardened option.
    """
    if parser is not None:
        if parser_kwargs:
            raise ValueError(
                "parser kwargs belong to the parser of this call, not to a "
                "parser which was built already: pass either parser= or the "
                "options, not both")
        return etree.fromstring(as_bytes(content), parser=parser)
    return etree.fromstring(
        as_bytes(content), parser=_parser_without_softening(**parser_kwargs))


def parse_untrusted_document(content, **parser_kwargs):
    """Like :func:`parse_untrusted`, but answers the document, not the root.

    A caller which needs the document object - to build an
    :class:`lxml.etree.XMLSchema` from it, to walk with absolute paths from
    ``/``, or to keep an ``ElementTree`` the way :func:`lxml.etree.parse`
    answered one - takes this instead of reading the file itself. The bytes are
    still taken by :func:`as_bytes` and handed over as a stream, so lxml never
    opens the path and never resolves a relative system literal against it.
    """
    return etree.parse(
        BytesIO(as_bytes(content)), parser=_parser_without_softening(**parser_kwargs))


def _parser_without_softening(**parser_kwargs) -> etree.XMLParser:
    """:func:`hardened_parser` for the options of one call, refusing a softening."""
    for option in HARDENED_OPTIONS:
        if option in parser_kwargs:
            raise ValueError(
                f"{option} is the policy of {__name__} and can not be set at a "
                "call site; use parse_trusted for a document this deployment "
                "wrote itself")
    return hardened_parser(**parser_kwargs)


def parse_trusted(content) -> etree._Element:
    """The root of a document which this deployment wrote itself.

    The lenient variant, and the only place the lxml defaults are opened on
    purpose: a stored XML backup of the registry or a schema shipped with the
    package is a product of this code. Do not use it for a response of a remote
    service, a posted request, an uploaded document or anything else a remote
    side controls - that is :func:`parse_untrusted`.

    It is lenient in one direction only: it opens lxml's own defaults, and it is
    the name of the caller which says a document earned that. A document which
    is not well-formed still raises, because a broken backup is a data fault
    worth naming rather than a parser setting to soften.
    """
    return etree.fromstring(as_bytes(content))
