"""The content identity of the documented sources (#1607, epic #1589).

Split out of ``mrmap_docs`` for one reason: the digest below is the reuse key of
a documentation artifact (ADR-0001 section 6), so the build that writes it and
the gate that re-computes it must read **one** implementation. Kept apart from
its caller because that caller imports docutils and the gate runs on a bare
checkout with nothing installed - which is also what makes the gate runnable
where the build is not.

The rule the digest encodes: a rename counts, a byte counts, nothing else does.
Two builds of one tree are then comparable by reading one field, and an artifact
cannot be presented as the documentation of a tree it was not built from.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

#: What a reader of the portal can actually see: prose and the build's own
#: configuration. Binaries are excluded on purpose - a picture is referenced by
#: the page that quotes it, and provenance records that reference.
SOURCE_SUFFIXES = (".rst", ".md", ".py")


def source_digest(root: Path, suffixes=SOURCE_SUFFIXES) -> str:
    """Content digest of the documented sources, ordered by path.

    Paths are digested as well as bytes: a rename that preserves every byte
    still changes the identity, because the page's URL moved.
    """
    digest = hashlib.sha256()
    for path in sorted(p for p in Path(root).rglob("*")
                       if p.suffix in suffixes and p.is_file()):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()
