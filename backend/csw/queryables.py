"""The queryables of the catalogue, answered by the metadata records themselves.

A ``GetRecords`` filter arrives as CQL text or as a FES document and
:meth:`registry.ows_lib.request.ogc_request.OGCRequest.filter_constraint` answers a
:class:`~django.db.models.Q` for it by mapping every queryable name onto a field of the
nameing dictionary -- see :meth:`csw.views.CswServiceView.get_field_map`. That Q was
applied to the two searchable projections of the records, whose columns were shaped for
it. Applied to the records themselves, two of its lookups cannot work and one is not
answered by a column anymore:

*   ``AnyText`` is the text of a record, which is the tsvector column of it. A ``=``
    becomes a containment over that column, which is what a vector is compared with. A
    ``LIKE`` becomes a pattern lookup, and a pattern lookup is a ``LIKE`` -- a
    ``UPPER(...) LIKE UPPER(...)`` for an ``ILIKE`` -- over the compared value, and
    postgres compares a vector with a tsquery and with nothing else. A pattern over the
    text of a record is asked of the texts the vector is tokenized out of instead:
    :data:`TEXT_FIELDS`. Which of the two spellings the client used is kept, so
    ``AnyText LIKE '%x%'`` stays case sensitive and ``AnyText ILIKE '%x%'`` stays not.
*   ``subject`` is a keyword of a record, and a record answers its keywords through a
    relation. The array the database maintains for the vector cannot answer this
    queryable: postgres has neither ``=`` nor ``LIKE`` over ``text[]``, so a filter
    could only ever compare an array with an array.
*   ``type`` is the kind of a record and the querysets of this module *are* that
    kind. The record tables have no column for it, so a queryset annotates its own kind
    as a constant: a request for ``type = 'dataset'`` answers the dataset records and
    no service records, which is what the queryable promised, without a column that only
    ever repeats the table it names.
"""

from django.db.models import Q, Value

from registry.expressions.search import client_search_query
from registry.models.metadata import (ApplicationMetadataRecord,
                                      DatasetMetadataRecord,
                                      ServiceMetadataRecord)

#: The value of the ``type`` queryable which selects the dataset records, and the ones
#: which select the service and the application records. All of them are the
#: ``hierarchyLevel`` of the ISO document a record was made of -- the value the mapping
#: of a record is chosen by, see ``registry/mappers/configs/dataset.py``,
#: ``registry/mappers/configs/service.py`` and
#: ``registry/mappers/configs/application.py``.
HIERARCHY_LEVEL_DATASET = "dataset"
HIERARCHY_LEVEL_SERVICE = "service"
HIERARCHY_LEVEL_APPLICATION = "application"

#: The queryable names a CSW client may filter by and the field of a metadata record
#: each is answered from. A name which is not a field of a record is answered by one of
#: the rules of this module's docstring, which is also why ``AnyText`` names the vector
#: and not a text: a search over several texts has to ask all of them at once.
FIELD_MAP = {
    "title": "title",
    "Title": "title",
    "dc:title": "title",
    "abstract": "abstract",
    "Abstract": "abstract",
    "dc:abstract": "abstract",
    "description": "abstract",
    # a keyword of a record, seen through the relation which carries them
    "subject": "keywords__keyword",
    # "creator": "",  # TODO: find out what the creator field is exactly represented inside the iso metadata record
    "coverage": "bounding_geometry",
    "ows:BoundingBox": "bounding_geometry",
    "date": "date_stamp",
    "dc:modified": "date_stamp",
    "modified": "date_stamp",
    "Modified": "date_stamp",
    "type": "hierarchy_level",
    "dc:type": "hierarchy_level",
    "Type": "hierarchy_level",
    "ResourceIdentifier": "resource_identifier",
    "identifier": "file_identifier",
    "Identifier": "file_identifier",
    # the vector of a record: every lookup which is not a containment is answered by
    # the texts it is built from, see search_filter
    "AnyText": "search_vector",
}

#: The texts a record is found by, which are the texts the vector of the record is
#: tokenized out of -- the same three relations the record viewsets search by, see
#: ``search_fields`` of ``registry/views/metadata.py``.
TEXT_FIELDS = ("title", "abstract", "keywords__keyword")

#: The name of the vector column of a record, which is what a search of a client is
#: asked of; :data:`registry.expressions.search.MetadataRecordSearchVector` builds it.
SEARCH_VECTOR = "search_vector"


def dataset_records():
    """Every dataset metadata record, as a search endpoint answers them."""
    return search_records(DatasetMetadataRecord, HIERARCHY_LEVEL_DATASET)


def service_records():
    """Every service metadata record, as a search endpoint answers them."""
    return search_records(ServiceMetadataRecord, HIERARCHY_LEVEL_SERVICE)


def application_records():
    """Every application metadata record, as a search endpoint answers them."""
    return search_records(ApplicationMetadataRecord,
                          HIERARCHY_LEVEL_APPLICATION)


def search_records(model, hierarchy_level: str):
    """The records of one kind, in the order a search endpoint answers them.

    Ordered by their primary key: a search answers the record tables as one result set,
    which is merged by that key, and a client paging through such a set has to see the
    same records on the same page every time.

    Distinct, because a filter on ``subject`` joins the keywords of a record and a
    record holding several matching keywords would appear once per keyword. The response
    of a ``GetRecords`` names the number of *records* matched, so the duplicates of a
    record have to go before anything is counted.
    """
    return model.objects.annotate(
        hierarchy_level=Value(hierarchy_level),
    ).order_by("pk").distinct()


#: The records of one kind, keyed by the value of the ``type`` queryable which
#: selects them -- the mapping the three querysets above spell out one by one.
RECORD_MODELS = {
    HIERARCHY_LEVEL_DATASET: DatasetMetadataRecord,
    HIERARCHY_LEVEL_SERVICE: ServiceMetadataRecord,
    HIERARCHY_LEVEL_APPLICATION: ApplicationMetadataRecord,
}


def page_records(rows) -> list:
    """The records the projected rows of a merged page are, as themselves.

    :func:`csw.elementsets.merged_page` answers a page as rows projected over
    all three record tables -- one of which names no record of the others --
    and this turns the kind, pk, identifier and backup document each row
    carries back into an unsaved instance of the model the row came out of. A
    ``GetRecords`` reads the stored document off the instance and names it by
    its identifier when that document cannot be served; both are fields the row
    already carries, so nothing of the record is re-read.
    """
    records = []
    for row in rows:
        record = RECORD_MODELS[row["hierarchy_level"]](pk=row["pk"])
        record.file_identifier = row["file_identifier"]
        record.xml_backup_file = row["xml_backup_file"]
        records.append(record)
    return records


def search_filter(constraint: Q) -> Q:
    """The constraint of a request, asked of a metadata record.

    The Q which the queryable mapping answers is aimed at a projection: the lookups of
    its leaves are the ones the columns of a projection took. This is the copy of it
    whose leaves the records answer; see the rules of this module's docstring.
    """
    return _rewrite(constraint)


def _rewrite(node: Q) -> Q:
    """A copy of a Q node with every leaf asked of a record.

    The tree of a Q is walked instead of rebuilt from the constraint, because the
    lookups which have to be answered differently can sit anywhere in it -- a
    ``subject`` and an ``AnyText`` of one request are combined with the rest of the
    filter, and only a leaf knows which of them it is.
    """
    return Q(
        *[_rewrite(child) if isinstance(child, Q) else _rewrite_leaf(*child)
          for child in node.children],
        _connector=node.connector,
        _negated=node.negated,
    )


def _rewrite_leaf(lookup: str, value):
    """One comparison of a filter, expressed on the fields of a record."""
    field, _, pattern_lookup = lookup.partition("__")
    if field != SEARCH_VECTOR:
        return Q(**{lookup: value})

    if pattern_lookup in ("", "exact"):
        # the containment a tsvector is compared with: postgres takes a tsquery on the
        # right hand side of it, which is what a search text of a client becomes here
        return Q(**{SEARCH_VECTOR: client_search_query(_text(value))})

    # A pattern lookup over a vector: postgres compares a vector with a tsquery and
    # nothing else, so the pattern is asked of the texts the vector was tokenized out
    # of. Which of the two spellings of a pattern the client chose -- LIKE, which is case
    # sensitive, or ILIKE, which is not -- is carried over with the lookup.
    result = Q()
    for text_field in TEXT_FIELDS:
        result |= Q(**{f"{text_field}__{pattern_lookup}": _text(value)})
    return result


def _text(value):
    """The text a filter carries, out of the expression the filter backend wrapped it in.

    The pygeofilter backend answers the right hand side of a comparison as a
    :class:`~django.db.models.Value`, and a tsquery is built of a text, not of an
    expression naming one.
    """
    if isinstance(value, Value):
        return value.value
    return value
