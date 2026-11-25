"""The portal build's own Sphinx extension (#1597, epic #1589).

One module carries the three things this portal needs and stock Sphinx does not
give it, because all three answer the same question - **what may a generated
page claim, and against what was that claim checked?**

**Offline rendering.** The portal builds with no database, no GDAL and none of
the backend's Python dependencies. Where the tree asks for an API reference,
``mrmap_autodoc`` decides what happens: ``"auto"`` (the default) asks whether the
application is importable and uses ``sphinx.ext.autodoc`` when it is, and
overrides the reference directives with a placeholder that names the module and
states why its reference is absent when it is not. ``"on"`` and ``"off"`` force
either side, so the docs image can fail closed on a genuinely broken reference
while a host that only wants prose stays green. The rule throughout is ADR-0001
section 11: a reader must never be able to mistake a missing section for an empty
one. This is also the fix for the five autodoc surfaces that had been failing as
warnings nobody read - ``registry.models.service``, ``registry.models.security``,
``registry.managers.service``, ``registry.proxy.wms_proxy`` and
``registry.proxy.wfs_proxy``.

**Diagrams without a network.** ``mrmap_diagrams = "static"`` - the default -
renders ``mermaid`` blocks as visible markup carrying the diagram source and
injects no script tag, so neither the build nor the published page contacts a
CDN. Graphviz renders through the local ``dot`` binary when one is installed and
falls back to the same visible-source treatment when it is not.
``mrmap_diagrams = "render"`` is the explicitly configured dependency the issue
allows: graphviz keeps using ``dot``, and mermaid uses ``sphinxcontrib.mermaid``
against a **vendored** renderer named by ``mrmap_mermaid_js``. Without that file
the build refuses rather than quietly loading a remote script.

**Build identity.** Every HTML build writes ``provenance.json`` beside its output
naming the toolchain versions, the digest of the documented sources, the version
and commit documented, and the autodoc and diagram modes the build actually
used. Two builds of one input are then comparable by reading one file - the only
form "reproducible" can take once a release gate consumes the artifact.

Every knob is declared here and set from ``conf.py``.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import platform
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path

from docutils import nodes
from docutils.parsers.rst import Directive, directives

#: Directives this module can stand in for while the backend is not importable.
AUTO_DIRECTIVES = (
    "automodule",
    "autoclass",
    "autofunction",
    "automethod",
    "autodata",
    "autoproperty",
    "autoexception",
)

#: Named in ``provenance.json``: a build is only reproducible against a named
#: version of each, and ``backend/.requirements/docs.txt`` pins exactly these.
TOOLCHAIN = (
    "sphinx",
    "myst-parser",
    "sphinx-rtd-theme",
    "sphinx-multiversion",
    "sphinxcontrib-mermaid",
    "sphinxcontrib-httpdomain",
    "docutils",
)

AUTODOC_MODES = ("auto", "on", "off")
DIAGRAM_MODES = ("static", "render")
MERMAID_RENDERER_FILENAME = "mrmap-mermaid-vendored.mjs"


def source_digest(root: Path, suffixes=(".rst", ".md", ".py")) -> str:
    """Content digest of the documented sources, ordered by path.

    Paths are digested as well as bytes: a rename that preserves every byte
    still changes the identity, because the page's URL moved.
    """
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*")
                       if p.suffix in suffixes and p.is_file()):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def documented_commit(source_root: Path) -> str | None:
    """The revision the build documents, or None when it cannot be named.

    CI names it (``GITHUB_SHA``), a local build asks git. Recording null beats
    recording a guess: a gate reads null as "not attributable", which is the
    honest reading of a build from a dirty or detached tree.
    """
    from_env = os.environ.get("GITHUB_SHA") or os.environ.get("MRMAP_DOCS_REVISION")
    if from_env:
        return from_env
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=source_root, capture_output=True, text=True, timeout=10, check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def toolchain_versions() -> dict:
    versions = {}
    for package in TOOLCHAIN:
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = None
    return versions


class _SourceDiagram(Directive):
    """Renders a diagram block as visible markup carrying its own source.

    This is what keeps the build and the published page offline: no script tag,
    no CDN, no browser-side fetch. The diagram source is the authoritative
    artifact - the thing a reader can paste into a renderer or put in a diff - so
    it is shown rather than hidden behind an image that may not be there.
    """

    has_content = True
    required_arguments = 0
    optional_arguments = 1
    final_argument_whitespace = True
    option_spec = {
        "alt": directives.unchanged,
        "align": directives.unchanged,
        "caption": directives.unchanged,
        "name": directives.unchanged,
        "config": directives.unchanged,
    }

    #: Set by the subclasses; names the block in the markup and in the title.
    language_name = "diagram"

    def run(self):
        source = "\n".join(self.content)
        container = nodes.container(classes=[
            "mrmap-diagram", f"mrmap-diagram--{self.language_name}"])
        container += nodes.paragraph(
            "", classes=["mrmap-diagram__title"],
            text=f"{self.language_name} diagram (source, not rendered in this build)")
        if "alt" in self.options:
            container += nodes.paragraph(
                "", classes=["mrmap-diagram__alt"], text=self.options["alt"])
        literal = nodes.literal_block(source, source)
        literal["language"] = self.language_name
        container += literal
        container += nodes.paragraph(
            "", classes=["mrmap-diagram__note"],
            text="Rendered offline by design: this build contacts no diagram "
                 "service and the published page loads no renderer script. The "
                 "source above is the artifact.")
        if "name" in self.options:
            self.add_name(container)
        return [container]


class MermaidSourceDiagram(_SourceDiagram):
    language_name = "mermaid"


class GraphvizSourceDiagram(_SourceDiagram):
    language_name = "graphviz"


class _ReferencePlaceholder(Directive):
    """Stands in for one reference directive while the backend is not importable.

    Deliberately loud. An empty section reads as "nothing to document"; this
    reads as "the reference of this module was not generated in this build",
    which is what happened.
    """

    has_content = True
    optional_arguments = 1
    final_argument_whitespace = True
    option_spec = {
        "members": directives.unchanged,
        "undoc-members": directives.flag,
        "private-members": directives.flag,
        "protected-members": directives.flag,
        "special-members": directives.unchanged,
        "show-inheritance": directives.flag,
        "inherited-members": directives.unchanged,
        "noindex": directives.flag,
        "member-order": directives.unchanged,
        "exclude-members": directives.unchanged,
        "imported-members": directives.flag,
        "annotation": directives.unchanged,
    }

    def run(self):
        if self.arguments:
            target = self.arguments[0].split()[0]
        elif self.content:
            target = self.content[0].split()[0]
        else:
            target = "<unnamed module>"
        container = nodes.container(classes=["mrmap-reference-unavailable"])
        container += nodes.paragraph(
            "", classes=["mrmap-reference-unavailable__title"],
            text="Reference not generated in this build")
        body = nodes.paragraph()
        body += nodes.Text("The reference of ")
        body += nodes.literal(text=target)
        body += nodes.Text(
            " is extracted from the application itself, and this build runs "
            "without the backend environment - no database, no GDAL, no "
            "application imports. The module is named here so the gap is "
            "visible instead of blank. Everything else on this page is derived "
            "from source and is complete in every build.")
        container += body
        return [container]


def _override_directives(app, name_and_class) -> None:
    for name, klass in name_and_class.items():
        app.add_directive(name, klass, override=True)


def backend_is_importable() -> bool:
    """Whether the application can actually be imported in this build.

    Imports the smallest thing autodoc needs - a backend module - and reports the
    answer, with ``sys.path`` restored either way. Deliberately not an import of
    ``MrMap.settings``: that would put Django and every database driver behind it
    on the path of a build meant to need none of them.
    """
    backend = Path(__file__).resolve().parents[3] / "backend"
    if not (backend / "registry" / "models" / "service.py").is_file():
        return False
    saved = list(sys.path)
    try:
        sys.path.insert(0, str(backend))
        importlib.invalidate_caches()
        importlib.import_module("registry.models.service")
    except Exception:
        return False
    finally:
        sys.path[:] = saved
    return True


def _configure_autodoc(app) -> str:
    """Decide the autodoc behaviour; return what was chosen, for provenance."""
    mode = (app.config.mrmap_autodoc or "auto").lower()
    if mode not in AUTODOC_MODES:
        raise ValueError(
            f"mrmap_autodoc must be one of {AUTODOC_MODES}, "
            f"got {app.config.mrmap_autodoc!r}")
    placeholders = {name: _ReferencePlaceholder for name in AUTO_DIRECTIVES}

    if mode == "off":
        _override_directives(app, placeholders)
        return "placeholders:forced-off"
    if mode == "on":
        # Fail closed: leave the real directives in place, so a module that
        # cannot be imported is an error the docs image sees rather than a
        # placeholder it ships.
        app.setup_extension("sphinx.ext.autodoc")
        return "autodoc:forced-on"

    if backend_is_importable():
        app.setup_extension("sphinx.ext.autodoc")
        return "autodoc:application"
    _override_directives(app, placeholders)
    return "placeholders:django-not-installed"


def _copy_vendored_mermaid(app, exception) -> None:
    if exception is not None or app.builder.format != "html":
        return
    source = Path(app.config.mrmap_mermaid_js).resolve()
    target = Path(app.outdir) / "_static" / MERMAID_RENDERER_FILENAME
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def _configure_diagrams(app) -> str:
    """Decide the diagram behaviour; return what was chosen, for provenance.

    Both directives are registered rather than only the ones the source tree
    mentions: a diagram can arrive through an ``{include}`` of a document outside
    ``source`` - which is how the design notes are rendered - and a block whose
    directive is missing is a build error, not a degraded page.
    """
    mode = (app.config.mrmap_diagrams or "static").lower()
    if mode not in DIAGRAM_MODES:
        raise ValueError(
            f"mrmap_diagrams must be one of {DIAGRAM_MODES}, "
            f"got {app.config.mrmap_diagrams!r}")

    if mode == "render":
        vendored = app.config.mrmap_mermaid_js
        if not vendored or not Path(vendored).is_file():
            raise ValueError(
                "mrmap_diagrams = 'render' asks for real mermaid rendering, which "
                "this build does locally from a vendored renderer. Set "
                "mrmap_mermaid_js (or MRMAP_DOCS_MERMAID_JS) to the path of that "
                "file. Loading a renderer from a CDN is not offered: a "
                "documentation build that phones home to draw a picture is the "
                "failure this mode exists to prevent.")
        app.setup_extension("sphinxcontrib.mermaid")
        app.config.mermaid_use_local = MERMAID_RENDERER_FILENAME
        app.connect("build-finished", _copy_vendored_mermaid)
        if shutil.which("dot"):
            app.setup_extension("sphinx.ext.graphviz")
        else:
            _override_directives(app, {"graphviz": GraphvizSourceDiagram})
        return "render"

    # static: graphviz still renders through a local `dot` when one exists -
    # that is offline, so refusing it would only make the docs worse.
    chosen = {"mermaid": MermaidSourceDiagram}
    # A mermaid block that arrives as a code block instead of the directive - the
    # form an ``{include}`` of a note outside ``source`` produces, because
    # ``myst_fence_as_directive`` applies to the including document - is then
    # highlighted as plain text: the source is the artifact, and Pygments has no
    # mermaid lexer to fail on.
    from pygments.lexers import TextLexer
    app.add_lexer("mermaid", TextLexer)
    if shutil.which("dot"):
        app.setup_extension("sphinx.ext.graphviz")
    else:
        chosen["graphviz"] = GraphvizSourceDiagram
    _override_directives(app, chosen)
    return "static"


def _write_provenance(app, exception) -> None:
    if exception is not None or not app.config.mrmap_provenance:
        return
    if app.builder.format != "html":
        return
    source_root = Path(app.srcdir)
    outdir = Path(app.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    provenance = {
        "schema": "mrmap.docs.provenance.v1",
        "project": app.config.project,
        "version": app.config.version,
        "release": app.config.release,
        "version_source": getattr(app.config, "mrmap_version_source", "unknown"),
        "language": app.config.language,
        "builder": app.builder.name,
        "documented_commit": documented_commit(source_root),
        "source_date_epoch": os.environ.get("SOURCE_DATE_EPOCH"),
        "python": platform.python_version(),
        "toolchain": toolchain_versions(),
        "source_digest": source_digest(source_root),
        "autodoc": getattr(app.config, "mrmap_autodoc_effective", "unknown"),
        "diagrams": getattr(app.config, "mrmap_diagrams_effective", "unknown"),
        "locales": list(app.config.mrmap_locales),
        "pages": (len(list(source_root.rglob("*.rst")))
                  + len(list(source_root.rglob("*.md")))),
    }
    (outdir / "provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def setup(app):
    app.add_config_value("mrmap_autodoc", "auto", "env")
    app.add_config_value("mrmap_diagrams", "static", "env")
    app.add_config_value("mrmap_mermaid_js", "", "env")
    app.add_config_value("mrmap_provenance", True, "env")
    app.add_config_value("mrmap_version_source", "unknown", "env")
    app.add_config_value("mrmap_locales", ["en"], "env")

    source_root = Path(app.srcdir)
    app.config.mrmap_autodoc_effective = _configure_autodoc(app)
    app.config.mrmap_diagrams_effective = _configure_diagrams(app)

    app.connect("build-finished", _write_provenance)
    return {"version": "1", "parallel_read_safe": True, "parallel_write_safe": True}
