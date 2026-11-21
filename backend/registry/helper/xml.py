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

Never keep a parser of this module as a module level object: lxml binds the
docloader of a document to the parser which read it, so one shared parser
instance would pin every document it ever read for the lifetime of the process,
which is the memory fault #1348 removed for the XML cache. Each call builds its
parser, and a caller which wants one instance for a family of documents gets it
from :func:`hardened_parser` and owns its lifetime.
"""
from io import BytesIO
from os import PathLike
from pathlib import Path

from lxml import etree

#: the options every untrusted document is parsed with (#1468)
HARDENED_OPTIONS = {
    "resolve_entities": False,
    "no_network": True,
}


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
    against that file's directory, and a document which declares an encoding is
    refused as ``str`` but decoded correctly as bytes.
    """
    if hasattr(content, "read"):
        return content.read()
    if isinstance(content, bytes):
        return content
    if isinstance(content, str):
        return content.encode("utf-8")
    if isinstance(content, PathLike):
        return Path(content).read_bytes()
    raise TypeError(
        f"can not read an XML document from {type(content).__name__}")


def parse_untrusted(content, *, parser=None, **parser_kwargs) -> etree._Element:
    """The root of a document which an external side wrote.

    An entity the document declares stays unexpanded and no declared system
    literal is fetched, so the tree carries neither the content of a local file
    nor a remote one, no matter what the document declares. A document which is
    not well-formed raises :class:`lxml.etree.XMLSyntaxError` like lxml does; a
    document without a root element answers ``None``, which is what lxml
    answers for whitespace.

    :param content: ``bytes``, ``str``, a path or a readable file object
    :param parser: an existing parser, e.g. from :func:`hardened_parser`, to
        read several documents with one instance without softening the policy
    :param parser_kwargs: further options for the parser of this call, which
        must not repeat the hardened ones
    """
    if parser is None:
        parser = hardened_parser(**parser_kwargs)
    return etree.fromstring(as_bytes(content), parser=parser)


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
        BytesIO(as_bytes(content)), parser=hardened_parser(**parser_kwargs))


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
