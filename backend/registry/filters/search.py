"""The search of a list endpoint, answered by the search vector of a record.

DRF's ``SearchFilter`` matches every word a client typed as ``UPPER(col) LIKE
'%word%'`` against every field the view names in ``search_fields``. Asked of a
metadata record, two of those fields are texts of the record and one is the keyword
behind its m2m relation, so postgres hash-joins the keyword relation of the whole
catalogue, applies the patterns to the joined rows and collapses the duplicate ids
the join produced -- and DRF's pagination asks exactly that statement for the
number of rows of the answer (#1029: the count is 92 % of the request, median 3.7 s
and worst 52.4 s on the list of service metadata records).

A record has answered its searchable representation as a column of its own since
#854 (:mod:`registry.expressions.search`), and that column carries a GIN index: the
words of its title, its abstract and every keyword of it are what a tsquery is
matched against, without a join and answered by one probe into that index. The CSW
(``csw/queryables.py``) and the MapBender search select records that way already;
the list endpoints of the records were the last consumers which did not.

A vector is compared with a tsquery and never with a text, so this changes what a
word of a search finds: a record is found by the words it holds, not by any piece
of a word. That is the vocabulary the other two search endpoints of this API
already answer with, and the one a client of a catalogue is looking in.
"""
from functools import reduce
from operator import or_

from django.contrib.postgres.search import SearchVectorField
from django.core.exceptions import FieldDoesNotExist
from django.db.models import Q
from django.db.models.constants import LOOKUP_SEP
from rest_framework.filters import SearchFilter

from registry.expressions.search import client_search_query


def is_search_vector(queryset, field_name):
    """Whether a searchable field names the column a record's vector is stored in.

    A field written with one of DRF's lookup prefixes, or naming a relation, is not
    a column of the searched model and so never a vector: only a column of it can
    be the generated vector of a record.
    """
    field_name = str(field_name)
    if field_name[:1] in SearchFilter.lookup_prefixes or LOOKUP_SEP in field_name:
        return False
    try:
        field = queryset.model._meta.get_field(field_name)
    except FieldDoesNotExist:
        return False
    # the vector is a generated column: a GeneratedField of a tsvector output field
    return isinstance(getattr(field, 'output_field', None), SearchVectorField)


class SearchVectorSearchFilter(SearchFilter):
    """The search of DRF, over the search vector where a view names one.

    A view asks for it by naming a search field which is a vector column; the
    search of every other view keeps the ``LIKE`` construction of the base, which
    is how a plain text column of a service or a keyword is searched. A view which
    names a vector beside a plain text keeps the base as well: the mixed statement
    is not answered by an index, so pretending otherwise would only hide the cost.
    """

    def vector_search_fields(self, queryset, view, request):
        """The vector fields of a view, or nothing when it does not search vectors.

        Read from the queryset and not from the view alone: whether a name is a
        vector column is a question of the model the searched queryset answers.
        """
        fields = [str(field) for field in self.get_search_fields(view, request) or ()]
        vectors = [field for field in fields if is_search_vector(queryset, field)]
        return vectors if len(vectors) == len(fields) else []

    def filter_queryset(self, request, queryset, view):
        fields = self.vector_search_fields(queryset, view, request)
        terms = self.get_search_terms(request)
        if not fields or not terms:
            return super().filter_queryset(request, queryset, view)

        # one tsquery for the words of the client, which is what keeps a search word
        # a word (registry/expressions/search.py) and the whole search one
        # containment over the vector: the words are ANDed by postgres, as the base
        # ANDs one LIKE block per word
        query = client_search_query(' '.join(terms))
        return queryset.filter(reduce(
            or_, (Q(**{field: query}) for field in fields)))
