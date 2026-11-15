from requests.exceptions import ConnectionError, Timeout


class UnknownMetadataKind(ValueError):
    """A metadata document whose record kind Mr. Map does not map.

    Raised by the ISO mapping selection for a ``hierarchyLevel`` which has no
    mapping config (#1260). The class exists to name the kind of what went
    wrong: the server answered, and answered a document - Mr. Map simply has no
    config for what the document says it is. That is a different thing from a
    document which was never answered, and it is a reason *not* to try again:
    the next attempt reads the same kind, so the failure is recorded instead of
    retried.

    It is a ``ValueError``, because that is how every caller of the mapping
    selection already reads an unmapped document.
    """


class PublishRefused(Exception):
    """The served ISO document of a record can not be regenerated from its row.

    The publish step of the metadata editor (#1244) derives the document the
    CSW serves from the fields a write just committed, through the write mapper
    of #1242. Whenever that derivation can not run to its end - the record is
    not the single node its own document names, the mapper can not read the
    stored bytes, or the write-back refuses the combination - the whole write
    is refused rather than committed: a stored record whose served document
    disagrees with it is exactly the state the readiness clarification of #1244
    forbids, and "no verdict" never passes as "valid" (the fail-closed posture
    #1241 shipped and #1243 kept).
    """


class MetadataFetchTimeout(Timeout):
    """The server behind a metadata link stayed silent past the timeout.

    The one failure which is no answer at all: the connection was accepted and
    then the document did not arrive within
    ``registry.settings.REGISTRATION_REQUEST_TIMEOUT_SECONDS`` (#1260). It is
    kept apart from a usable-but-wrong answer (``NoContent`` names the status
    which was answered) and from an unmappable one (``UnknownMetadataKind``
    names the kind) because "the server did not answer" and "the server
    answered 404" are different things for the person who has to fix the
    reference.

    A requests ``Timeout``, so ``BackgroundProcessBased.autoretry_for`` covers
    it: silence is the one failure of this family which another attempt can
    actually fix.
    """


class MetadataFetchUnreachable(ConnectionError):
    """The server behind a metadata link refused or lost the connection.

    The other failure without an answer: nothing listened, the connection was
    reset, or the retry budget of the adapter ran out before a connection
    stood (#1260). Unlike ``MetadataFetchTimeout`` the server did answer the
    handshake with "not here" - which is why the two are named apart, even
    though both are transient and both are retried: a ``ConnectionError`` puts
    them under ``BackgroundProcessBased.autoretry_for``.
    """
