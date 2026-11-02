"""Expressions which answer the searchable representation of a metadata record.

A stored generated column is computed by the database: its statement is stored in the
catalog and evaluated again for every row which is written. Two things which are
normal in a query are ruled out by that:

*   **parameters** -- the statement of a generated column takes none, so a
    configuration or an empty string cannot be passed as one. This is why
    :class:`django.contrib.postgres.search.SearchVector` cannot define such a column:
    it sends its text configuration and its coalescing values as parameters and
    postgres refuses them inside a generation expression with ``there is no parameter
    $1``.
*   **every function which is not immutable** -- ``to_tsvector(text)`` (the one
    argument variant, which takes the configuration of the connection), ``concat(...)``
    and everything which turns an array into a text (``array_to_string`` as well as the
    text representation of an array) are only stable; ``to_tsvector(regconfig, text)``,
    ``||`` and ``array_to_tsvector(text[])`` are immutable.

What these expressions answer are the words a record is found by: the text a record
answers its consumers with, tokenized into words, plus the words of every keyword of
the record. The keywords reach the vector through the array which the database
maintains for them (:mod:`registry.migrations.0021_metadatarecords_keywords_list`), so
that a record which was just written is searchable without anything rebuilt.
"""
from django.contrib.postgres.search import SearchQuery, SearchVectorField
from django.db.models.expressions import F, Func
from django.db.models.fields import TextField

#: The text search configuration the vectors of the records are built with. Named once:
#: a record which was indexed with one configuration cannot be found by a query which
#: uses another one, so a query has to name the very same configuration through
#: :data:`TEXT_CONFIGURATION_NAME`.
TEXT_CONFIGURATION_NAME = "english"
TEXT_CONFIGURATION = f"'{TEXT_CONFIGURATION_NAME}'::regconfig"


class CoalesceEmpty(Func):
    """The text an expression answers, or an empty string instead of a null.

    ``||`` is strict: one null would make the whole vector null and the record not
    findable at all. Which of the columns of a record can hold a null is a decision of
    the model and not of this expression, and a nullable text which is not guarded here
    would silently make every record which has one unfindable.
    """

    template = "COALESCE(%(expressions)s, '')"
    output_field = TextField()


class ConcatText(Func):
    """Several pieces of text as one string, separated by a blank.

    ``||`` is the immutable concatenation of postgres; ``concat(...)`` is only stable
    and cannot be used in a generation expression.
    """

    template = "%(expressions)s"
    arg_joiner = " || ' ' || "
    output_field = TextField()


class ToTsVector(Func):
    """The vector of a text, in the configuration this module names.

    The configuration is written into the statement instead of being passed as a
    parameter, which is what allows the expression to be a generated column.
    """

    function = "TO_TSVECTOR"
    template = f"%(function)s({TEXT_CONFIGURATION}, %(expressions)s)"
    output_field = SearchVectorField()


class KeywordsAsText(Func):
    """The keywords of a record as the text their words are tokenized out of.

    An array has no immutable way to become a text: ``array_to_string`` and the text
    representation of an array are both only stable. The array of the keywords of a
    record has an immutable way to become *something else* which is a text though --
    ``array_to_tsvector`` answers a vector of its entries and the text representation
    of a vector is immutable --, so the entries go through a vector to become the text
    :class:`ToTsVector` takes apart into the words of every keyword.

    ``array_to_tsvector`` is the only immutable way out of the array and it refuses an
    array holding an empty string or a null. That is the shape the database maintains
    for the keywords of a record: ``registry_keyword`` has not allowed a blank keyword
    since ``0016_enforce_non_blank_keywords`` and the trigger which maintains the array
    excludes a blank keyword as well.
    """

    template = "CAST(ARRAY_TO_TSVECTOR(%(expressions)s) AS TEXT)"
    output_field = TextField()


class ConcatVectors(Func):
    """Several vectors as one, which is the immutable `tsvector_concat`."""

    template = "%(expressions)s"
    arg_joiner = " || "
    output_field = SearchVectorField()


class MetadataRecordSearchVector(ConcatVectors):
    """The searchable representation of a metadata record.

    The text a record answers its consumers with and the words of its keywords, as one
    vector: the words a searchable projection of the record answered before the vector
    became a column of the record itself.
    """

    #: the text of the record which is worth finding, in the order the projection
    #: concatenated it
    TEXT_FIELDS = ("title", "abstract", "file_identifier", "code", "code_space")
    KEYWORDS_FIELD = "keywords_list"

    def __init__(self):
        super().__init__(
            ToTsVector(ConcatText(*(
                CoalesceEmpty(F(name)) for name in self.TEXT_FIELDS))),
            ToTsVector(KeywordsAsText(F(self.KEYWORDS_FIELD))),
        )


def client_search_query(text: str) -> SearchQuery:
    """The search text of a client as the tsquery a record is matched with.

    A client searches words, it does not write a tsquery: ``plainto_tsquery`` is what
    :class:`~django.contrib.postgres.search.SearchQuery` answers by default and what
    keeps a search word a word, so a ``&``, a ``:`` or a ``%`` which found its way into
    a search field cannot break the statement.

    The configuration is named explicitly, which is the whole point of this function:
    without it postgres takes the one of the connection, and a record whose vector was
    built with :data:`TEXT_CONFIGURATION_NAME` is not found by a query which stems its
    words by another one.
    """
    return SearchQuery(str(text or ""), config=TEXT_CONFIGURATION_NAME)
