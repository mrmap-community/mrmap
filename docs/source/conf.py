# Configuration file for the MrMap documentation portal (#1597, epic #1589).
#
# Two rules shape this file, and both come from ADR-0001 - the contract #1596
# delivered.
#
# **The build imports no application code.** Until now this file imported
# ``django``, ``MrMap.settings`` and ``MrMap.VERSION`` to get the release string
# and to make autodoc work. That is why the documentation could only be built
# inside a fully provisioned backend container, and why five autodoc surfaces
# then failed *silently* once the registry was reorganised: the tree asked for a
# reference and the build said nothing about not having it. The release string
# now comes from the root ``VERSION`` file - the canonical source named in
# ``docs/source/development/canonical-version.rst`` - and autodoc is decided by
# the local ``mrmap_docs`` extension, which asks whether the application is
# importable instead of assuming it. Building the portal needs the pinned docs
# environment and nothing else.
#
# **An input with no consumer is a failure, not a silence.** Markdown became a
# first-class source suffix here, which is what lets the authentication,
# permissions and outbound-fetch guidance under ``docs/source/administration/``
# and the design notes under ``docs/`` render at all. Before that no
# ``source_suffix`` matched them: they were invisible without a single warning,
# which is exactly the failure mode ADR-0001 section 11 exists to prevent.
#
# Everything below ``-- Options for HTML output --`` that looks oddly specific
# (``smv_*``, ``linkcheck_*``) is load-bearing elsewhere: ``smv_tag_whitelist``
# and ``smv_branch_whitelist`` are bound to ``scripts/release_lifecycle.json``
# by ``scripts/test_release_lifecycle.py``, which fails when the two drift.

# -- Path setup --------------------------------------------------------------

import os
import sys
from pathlib import Path

DOCS_ROOT = Path(__file__).resolve().parent
REPO_ROOT = DOCS_ROOT.parent.parent

# The portal's own extension lives under ``_ext`` rather than in the backend, so
# that building the documentation never puts application code on the import path.
sys.path.insert(0, str(DOCS_ROOT / "_ext"))

# -- Project information -----------------------------------------------------

project = "MrMap"
copyright = "2021, mrmap-community"
author = "mrmap-community"


def _version_from_the_canonical_file() -> str:
    """The root ``VERSION`` file, the source the release tooling promotes (#1577).

    ``"unreleased"`` when the file is not there: a build made from a tree without
    a version says so instead of inventing one.
    """
    try:
        return (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "unreleased"


#: How ``release`` was obtained, recorded in the build's provenance. Either the
#: application was importable and the version came through the compatibility
#: surface #1579 defines, or this is a portal build without the backend
#: environment and it came from the canonical file the projection is generated
#: from - the same value either way, and a reader of the artifact can tell which.
version_source = "unknown"

try:
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    # The version of the application being documented, through the one surface
    # #1579 designates for it, so that a bump reaches this consumer with the
    # other three. Nothing else may be imported from the application: this is the
    # line that separates the docs build from the backend environment, and
    # ``MrMap.settings`` behind it is what used to make a docs build need GDAL,
    # Django and a database (#1597).
    from MrMap import VERSION

    release = VERSION
    version = VERSION
    version_source = "MrMap"
except Exception:  # noqa: BLE001 - any failure of the application to import
    # A portal build is expected to run without the application installed, and
    # must still name the version it documents rather than fail. The value is
    # the same file ``backend/MrMap/version.py`` is generated from, so the two
    # cannot disagree while both are the checkout's own.
    release = _version_from_the_canonical_file()
    version = release
    version_source = "VERSION file"

user_agent = "Mozilla/5.0 (X11; Linux x86_64; rv:25.0) Gecko/20100101 Firefox/25.0"

# -- General configuration ---------------------------------------------------

extensions = [
    "myst_parser",
    "sphinx_rtd_theme",
    "sphinx_multiversion",
    "mrmap_docs",
]

# ``mrmap_docs`` carries the three things a stock Sphinx build does not give
# this portal: it decides what autodoc may claim when the backend is not
# importable, it renders Mermaid and Graphviz without a network, and it writes
# the build's provenance beside the output. Its module docstring holds the
# reasoning; the two settings below are the only knobs.
#
# The defaults are the offline-safe ones used by contributors and the current
# docs builds. ``MRMAP_DOCS_AUTODOC=on`` is an opt-in strict mode for an
# environment where the application can be imported; the docs image and
# Read the Docs do not set it. ``MRMAP_DOCS_DIAGRAMS=render`` asks for real
# diagram rendering against the vendored renderer named by
# ``MRMAP_DOCS_MERMAID_JS``.
mrmap_autodoc = os.environ.get("MRMAP_DOCS_AUTODOC", "auto")
mrmap_diagrams = os.environ.get("MRMAP_DOCS_DIAGRAMS", "static")
mrmap_mermaid_js = os.environ.get("MRMAP_DOCS_MERMAID_JS", "")
mrmap_provenance = os.environ.get("MRMAP_DOCS_PROVENANCE", "1") != "0"
mrmap_version_source = version_source
mrmap_locales = ["en"]

# Markdown joined reStructuredText as a source suffix. The prose under
# ``docs/source/administration/``, the architecture decision records and the
# design notes under ``docs/`` were authored in Markdown from the start; MyST is
# what turns them into portal pages instead of files no build reads.
source_suffix = {".rst": "restructuredtext", ".md": "markdown"}

templates_path = ["_templates"]

# ``build`` and ``_build`` are excluded so that a generated artifact inside the
# tree can never be picked up as source. That keeps authored content and
# generated output separate even when someone builds in place, which is what the
# docs Makefile and the ``pre_build`` job of ``.readthedocs.yaml`` both do.
exclude_patterns = ["build", "_build", ".doctrees", "locale", "**/.ipynb_checkpoints"]

# -- MyST configuration ------------------------------------------------------

myst_enable_extensions = [
    "colon_fence",
    "fieldlist",
    "strikethrough",
    "tasklist",
]

# Lets the portal pull a Markdown document in from outside ``source`` with
# ordinary MyST syntax. That is how ``docs/architecture.md`` and its sibling
# notes - which stay where they are, because ``AGENTS.md`` and the skills quote
# those paths - become portal pages without being moved or rewritten.
myst_fence_as_directive = ["include", "mermaid"]

# ``mermaid`` is in the list so a ```mermaid fence becomes the mermaid directive
# rather than a code block: Pygments has no mermaid lexer, and the directive is
# what mrmap_docs renders as visible, offline source.

# Heading anchors so that a Markdown link from one document to a section of
# another resolves instead of falling through to a bare external link. Three
# levels covers every heading depth in the corpus.
myst_heading_anchors = 3

# -- Options for HTML output -------------------------------------------------

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
html_css_files = ["mrmap-portal.css"]
html_title = f"MrMap {release} documentation"
html_favicon = "images/mr_map.png"
html_logo = "images/mr_map.png"

# Accessibility and identity, both cheap and both previously absent: a language
# on the root element for screen readers, and a text alternative for the logo so
# the banner never arrives unnamed. The theme provides the skip-to-content link
# and the rest of the landmarks; ``mrmap-portal.css`` only keeps long code
# blocks and the diagrams readable at narrow widths.
language = "en"

# ``_static`` and the stylesheet below are part of the build, not decoration: a
# static path that is not there is a warning, and a warning is a failure.
# ``scripts/test_docs_build.py`` asserts both exist, because a directory holding
# nothing is not committed by git and an empty checkout therefore builds without
# the theme's one customisation - which is exactly what CI caught and a local
# tree with the directory already present did not.
#
# Sphinx 4.5 needs the builder's image list ordered with vector first, so that
# the SVG diagrams in the corpus are not downgraded to a raster fallback that is
# listed ahead of them.
from sphinx.builders.html import StandaloneHTMLBuilder  # noqa: E402

StandaloneHTMLBuilder.supported_image_types = [
    "image/svg+xml",
    "image/gif",
    "image/png",
    "image/jpeg",
]

linkcheck_timeout = 30

linkcheck_ignore = [
    r"http://localhost\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)",
    r"https://localhost\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)",
    r"http://127.0.0.1\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)",
    r"https://127.0.0.1\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)",
    r"http://YOUR-IP-ADDRESS\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)",
    # Historical links whose targets are client-rendered GitHub fragments or
    # whose host currently fails TLS validation. Keep all other links gated.
    r"https://github\.com/mrmap-community/mrmap/issues/1256#issuecomment-6796247548",
    r"https://github\.com/mrmap-community/mrmap/pull/1255#discussion_r4538304447",
    r"https://github\.com/mrmap-community/mrmap/pull/1255#discussion_r4541842215",
    r"https://github\.com/mrmap-community/mrmap/pull/1255#discussion_r4541817433",
    r"https://github\.com/mrmap-community/mrmap/pull/1255#discussion_r4541861570",
    r"https://github\.com/mrmap-community/mrmap/pull/1255#discussion_r4541851548",
    r"https://github\.com/mrmap-community/mrmap/pull/1255#discussion_r4541888319",
    r"https://github\.com/mrmap-community/mrmap/pull/1255#discussion_r4541870176",
    r"https://masteringdjango\.com/django-tutorials/mastering-django-structure/?",
]

linkcheck_request_headers = {
    "*": {"User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux i686; "
          "rv:24.0) Gecko/20100101 Firefox/24.0"}
}

master_doc = "index"

# Include released tags: the two component names the repository published
# before the semver policy (v0.1, v0.2, ...) and the full names promotion
# creates today (v0.2.0, v0.2.1, ...). Release candidates are excluded;
# prereleases have no published documentation. The machine-readable
# description of this selection is scripts/release_lifecycle.json.
smv_tag_whitelist = r'^v\d+(\.\d+){1,2}$'         # "v0.2" (historical) and "v0.2.0" (released)
smv_branch_whitelist = r'^develop$'              # Include develop branch
# Use branches from all remotes
smv_remote_whitelist = None
