(design-notes)=

# Design notes

The reasoning behind the features, written while they were being decided. These
pages are **not** generated and not summarised: each is one hand-authored
Markdown note under ``docs/`` in the repository, included into the portal
verbatim by the page that names it.

The notes were always part of the corpus and never part of the portal. Before
#1597 the build loaded no Markdown parser, so eight notes totalling more than
1 600 lines - beside two image manifests - were invisible to a reader while
``AGENTS.md``, the README and the project's own skills quoted them as authority.
Rendering them is the whole of this section; editing them is not, which is why
no page here carries prose of its own.

Two conventions to read them with:

- **Provenance is stated, not assumed.** Several notes carry images marked
  ``CURRENT`` or ``PROPOSED``. Those are renderings of the implemented
  components or of a proposal, produced from the source at a named commit, and
  the manifest beside them under ``docs/images/`` says which is which and when
  it was made. They are not screenshots of a running deployment, and the notes
  say so themselves.
- **A note is the historical record.** Several are explicitly research, an audit
  or a proposed contract, and one describes a decision a later review round
  superseded. Where a note and the running software disagree, the implementation
  page in the relevant section is the authority for the present and the note is
  the record of how it got there.

| Page | What it settles |
| --- | --- |
| architecture | The domain in one read: the service and metadata aggregates, update jobs, monitoring, the attention list and the security proxy. This is the note the project's own ``AGENTS.md`` files and skills point an implementer at. |
| metadata-identity | How a record keeps its identity across harvests and updates: the decision record of #982 on identity, relationships, precedence and enum conventions, including the correction the later review rounds forced. |
| metadata-collection-design | The audit and design behind registering an OGC service and collecting the metadata it links. Research and design only - the implementation is where the usage and development pages say it is. |
| metadata-editing | How a record is authored today: the write path and what it guarantees, the authoring profiles, when validation runs, what a save does to the served document, and what the first version deliberately does not do. |
| metadata-editor-design | The research and gap analysis that shaped the editor, with the comparison mockups. The mockups are proposals and the evidence grades say what was verified - read the page above for the implemented design. |
| ows-context | The OGC OWS Context GeoJSON profile the instance exports at ``/mrmap-proxy/ows/<id>`` and the viewer consumes. |
| ows-context-interoperability | The acceptance contract for the exported OWS Context against the clients that consume it. A proposed clarification, not an assertion that every row of it is implemented. |
| live-service-previews | The live preview card on a service overview: what it fetches, what it cancels, and which state belongs to the preview rather than to the viewer. |
| design/images/metadata-collection/README | The manifest beside those pictures: which file renders the implemented interface and which a proposal, and from which commit it was made. |
| design/images/metadata-editor/README | The manifest beside those pictures: which file renders the implemented interface and which a proposal, and from which commit it was made. |

```{toctree}
:hidden:
:maxdepth: 1

architecture
metadata-identity
metadata-collection-design
metadata-editing
metadata-editor-design
ows-context
ows-context-interoperability
live-service-previews
images/metadata-collection/README
images/metadata-editor/README
decisions/index
```
