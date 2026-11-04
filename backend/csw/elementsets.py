"""The element sets and the sorting a ``GetRecords`` answers with (#911).

Two request parameters of ``GetRecords`` shape the response around the records:

``csw:ElementSetName`` (10.8.4.9, Table 65)
    Which view of a record the request asks for. The value is an ``ElementSetType``
    -- one of ``brief``, ``summary`` or ``full`` -- and the element defaults to
    ``summary`` (CSW-discovery.xsd, the ``default`` of the global ``ElementSetName``
    element; the KVP binding synthesizes the same default, see
    :meth:`registry.ows_lib.request.ogc_request.OGCRequest.build_get_records_from_get`).
    A value which is none of the three is refused with ``InvalidParameterValue``.

    The views themselves are defined for the ``csw:Record`` information model
    (record.xsd: ``BriefRecordType``, ``SummaryRecordType``, and ``RecordType``
    for the whole of it); a profile answers its own representation of them. This
    endpoint answers ``gmd:MD_Metadata`` documents, so the non-full views are the
    stored document of a record pruned down to the elements the DCMI view maps to
    in ISO 19139:

    *   ``brief`` is ``dc:identifier``, ``dc:title``, ``dc:type`` and the bounding
        box -- ``fileIdentifier``, the citation title, the ``hierarchyLevel`` and
        the identification's ``extent``;
    *   ``summary`` adds ``dc:subject``, ``dct:abstract`` and the record dates --
        ``descriptiveKeywords``/``keyword``, ``abstract``, ``dateStamp`` and the
        citation ``date``;
    *   ``full`` is the document as it is stored.

    The set actually answered is named by the ``elementSet`` attribute of
    ``SearchResults`` (Table 66 -- the attribute is ``elementSet``, not the
    request parameter's ``ElementSetName``).

``ogc:SortBy`` (10.8.4.9)
    Which queryable the result set is ordered by, ascending or descending, before
    it is paged. Both bindings carry the request the same way -- the KVP binding
    embeds a ``csw:SortBy`` in the request it synthesizes -- so the sorting is
    read from the request element and mapped onto the ORM: every sortable queryable
    orders every record source by that expression and the merge of the sources
    compares records by it too. A queryable which is not sortable -- a text a
    pattern is searched with, a geometry, a keyword the record reaches over a
    relation -- is refused with ``InvalidParameterValue``, which 10.8.4.9 leaves
    for a property a catalogue does not sort on.
"""

from csw.queryables import FIELD_MAP
from django.db.models import F
from django.db.models.functions import Lower
from functools import cmp_to_key
from lxml import etree

from registry.ows_lib.xml.consts import NAMESPACE_LOOKUP

NS = {"csw": NAMESPACE_LOOKUP["csw_2_0_2"], "ogc": NAMESPACE_LOOKUP["ogc"]}

#: The element sets of ``ElementSetType`` (CSW-discovery.xsd).
ELEMENT_SETS = ("brief", "summary", "full")

#: The element set of a request which names none (10.8.4.9 and the ``default``
#: of the ``ElementSetName`` element).
DEFAULT_ELEMENT_SET = "summary"

#: The fields of a record no ``GetRecords`` can sort on: the keyword of a record
#: is reached over a many-to-many relation, which would multiply the records it
#: sorts; the search vector of a record is compared with a tsquery and answers no
#: order; and a geometry cannot be compared by the merge which orders the pages of
#: the record tables against each other.
NOT_SORTABLE = frozenset({"keywords__keyword", "search_vector", "bounding_geometry"})

#: The fields a record answers as a date rather than as a text; the text of a
#: field is ordered case-insensitively (see :func:`apply_sort`), its date is
#: compared as it is.
DATETIME_FIELDS = frozenset({"date_stamp"})


def requested_element_set(xml_request) -> str:
    """The ``ElementSetName`` of a request, as its client spelled it.

    The empty string for a request which names none -- which is the default of
    the specification rather than an error, so the view applies
    :data:`DEFAULT_ELEMENT_SET` to it. Both bindings are answered by the request
    element: the KVP binding carries the parameter inside the request it
    synthesizes, the XML binding inside the document it posts.
    """
    values = xml_request.xpath(
        "/csw:GetRecords/csw:Query/csw:ElementSetName/text()", namespaces=NS)
    return (values[0] if values else "").strip()


def sortable_field(property_name: str):
    """The field of a record a queryable is sorted on, or ``None``.

    The name is looked up in the queryable mapping the constraint is looked up
    in -- the queryables are one vocabulary -- so that a sortby of ``dc:title``
    orders by the same column a filter on ``dc:title`` filters. The values are
    compared case-insensitively, as the operation of the endpoint compares its
    queryables elsewhere.
    """
    field = FIELD_MAP.get(property_name) or FIELD_MAP.get(property_name.lower())
    if field is None or field in NOT_SORTABLE:
        return None
    return field


def sortable_properties() -> list:
    """The queryable names which answer :func:`sortable_field`."""
    return [name for name, field in FIELD_MAP.items() if field not in NOT_SORTABLE]


def requested_sort_by(xml_request) -> list:
    """``[(property_name, descending), ...]`` of the request's ``ogc:SortBy``.

    The KVP binding parses ``title:A,date:D`` into these ``SortProperty`` elements
    before the request is answered (see ``parse_sortby_param``), so this reads one
    binding rather than two. An absent ``SortOrder`` is ascending, which is the
    ``SortOrder`` the KVP parser leaves out.
    """
    sorts = []
    for sort_property in xml_request.xpath(
            "/csw:GetRecords/csw:Query/csw:SortBy/ogc:SortProperty", namespaces=NS):
        names = sort_property.xpath("ogc:PropertyName/text()", namespaces=NS)
        orders = sort_property.xpath("ogc:SortOrder/text()", namespaces=NS)
        sorts.append((
            (names[0] if names else "").strip(),
            (orders[0] if orders else "ASC").strip().upper().startswith("D"),
        ))
    return sorts


#: The fields of a record source which are no column but an annotation of it
#: (the ``type`` queryable, see ``csw/queryables.py``); they are carried by every
#: queryset of the sources and so never belong into ``only()``.
ANNOTATED_FIELDS = frozenset({"hierarchy_level"})


def loaded_fields(sort_specs) -> list:
    """The columns the answer of a page has to carry.

    The pk and the document of a record always; the field of every sort criterion
    too, because the merge of the record sources compares the records it
    merges by the very values the database ordered its half of the page by.
    """
    fields = ["pk", "xml_backup_file"]
    fields += [
        field
        for field in dict.fromkeys(field for field, _ in sort_specs)
        if field not in ANNOTATED_FIELDS
    ]
    return fields


def apply_sort(queryset, sort_specs):
    """Order one record source by the request's sorting, ready for ``merge_sorted``.

    Every sort criterion is annotated before it is ordered by: the sources answer
    their records ``DISTINCT``, and postgres demands an ``ORDER BY`` expression
    of a distinct query to stand in the select list too -- which an annotation
    always does. Text is ordered over ``LOWER(...)``: the collation of the cluster
    orders ASCII case-insensitively, and the python merge which interleaves the
    sources cannot know that collation -- it compares casefolded copies
    instead, which orders the same text the same way whatever the collation is,
    once the database has lowercased its side too.

    Nulls need no clause: postgres orders a null as the greatest value of either
    direction (``NULLS LAST`` ascending, ``NULLS FIRST`` descending) and
    :func:`_compare_values` mirrors exactly that.
    """
    if not sort_specs:
        # the paging order without a SortBy: the primary key, as csw/queryables.py
        # hands the sources out
        return queryset.order_by("pk")
    ordering = []
    for index, (field, descending) in enumerate(sort_specs):
        alias = f"csw_sort_{index}"
        expression = F(field) if field in DATETIME_FIELDS else Lower(field)
        queryset = queryset.annotate(**{alias: expression})
        ordering.append(F(alias).desc() if descending else F(alias).asc())
    return queryset.order_by(*ordering, "pk")


def merge_sorted(records, sort_specs) -> list:
    """The records of all sources merged into the order the sources answered.

    Every source was sliced and ordered by :func:`apply_sort`, which is a total
    order over ``(sort fields, pk)``; a record which belongs to the first ``n``
    records of the merged result belongs to the first ``n`` of its own source
    under the same order, so merging the limited slices answers the page.
    """
    return sorted(records, key=cmp_to_key(
        lambda a, b: _compare_records(a, b, sort_specs)))


def _compare_records(a, b, sort_specs) -> int:
    for field, descending in sort_specs:
        result = _compare_values(
            getattr(a, field), getattr(b, field), field, descending)
        if result:
            return result
    # the tie breaker the ORDER BY of the sources ends with, too
    return (a.pk > b.pk) - (a.pk < b.pk)


def _compare_values(value_a, value_b, field, descending) -> int:
    # postgres orders a null as the greatest value of the column whichever way the
    # column is ordered -- ascending puts it last, descending puts it first
    if value_a is None or value_b is None:
        if value_a is value_b is None:
            return 0
        greatest = 1 if value_a is None else -1
        return -greatest if descending else greatest
    if field not in DATETIME_FIELDS:
        value_a, value_b = str(value_a).casefold(), str(value_b).casefold()
    if value_a == value_b:
        return 0
    lesser = -1 if value_a < value_b else 1
    return -lesser if descending else lesser


# The element paths of a gmd:MD_Metadata document the brief and the summary view
# keep, in the local names of ISO 19139 (a "*" matches any element name, which is
# how the view reaches past the choice of an identification -- MD_DataIdentification
# or MD_MaintenanceInformation -- and past the concrete type of a citation). The
# mapping is the DCMI view of record.xsd read onto the fields a 19139 document
# answers it with: dc:identifier -> fileIdentifier, dc:title -> the citation
# title, dc:type -> hierarchyLevel, ows:BoundingBox -> the extent of the
# identification, dc:subject -> its descriptiveKeywords/keyword, dct:abstract ->
# its abstract, and dct:modified -> dateStamp and the citation date, which is
# where 19139 keeps the dates of a resource.
_KEEP_PATHS = {
    "brief": (
        ("fileIdentifier",),
        ("hierarchyLevel",),
        ("identificationInfo", "*", "citation", "*", "title"),
        ("identificationInfo", "*", "extent"),
    ),
    "summary": (
        ("fileIdentifier",),
        ("hierarchyLevel",),
        ("dateStamp",),
        ("identificationInfo", "*", "citation", "*", "title"),
        ("identificationInfo", "*", "citation", "*", "date"),
        ("identificationInfo", "*", "abstract"),
        ("identificationInfo", "*", "descriptiveKeywords"),
        ("identificationInfo", "*", "keyword"),
        ("identificationInfo", "*", "extent"),
    ),
}


def project_gmd_record(record, element_set):
    """A stored document of a record, narrowed to the requested element set.

    ``full`` is the document itself; the other two views are answered by pruning
    it (10.8.4.9: a profile answers its element sets over its own representation).
    The document of a record is its ``MD_Metadata`` element -- which a harvested
    backup may carry inside the envelope of the response it arrived in, so the
    view prunes every ``MD_Metadata`` the document holds and leaves an envelope
    around them as it stands. A document which carries no ``MD_Metadata`` is not
    a 19139 record view and is answered as it is. A container which keeps nothing
    is dropped rather than answered empty -- the elements a view does keep are
    complex types which demand their own content.
    """
    if element_set == "full":
        return record
    keep_paths = _KEEP_PATHS[element_set]
    if etree.QName(record).localname == "MD_Metadata":
        _prune_children(record, (), keep_paths)
    else:
        for metadata in record.findall(".//{*}MD_Metadata"):
            _prune_children(metadata, (), keep_paths)
    return record


def _prune_children(element, path, keep_paths) -> bool:
    """Whether at least one kept element survives below ``element``.

    Prunes the children of ``element``; ``path`` is the local-name path of
    ``element`` itself. A child whose path is a kept path keeps its whole subtree,
    a child on the way to one is pruned in turn, a child on no way to one goes.
    """
    kept = False
    for child in list(element):
        if not isinstance(child.tag, str):
            continue  # a comment or processing instruction of the document
        child_path = path + (etree.QName(child).localname,)
        if any(_matches(kp, child_path) for kp in keep_paths):
            kept = True
        elif any(_on_the_way(kp, child_path) for kp in keep_paths):
            if _prune_children(child, child_path, keep_paths):
                kept = True
            else:
                element.remove(child)
        else:
            element.remove(child)
    return kept


def _matches(keep_path, path) -> bool:
    """Whether ``path`` names a kept element, "*" matching any name."""
    return len(keep_path) == len(path) and all(
        keeper == "*" or keeper == name
        for keeper, name in zip(keep_path, path))


def _on_the_way(keep_path, path) -> bool:
    """Whether ``keep_path`` continues below ``path``, "*" matching any name."""
    if len(keep_path) <= len(path):
        return False
    return all(keeper == "*" or keeper == name
               for keeper, name in zip(keep_path, path))
