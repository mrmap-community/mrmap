"""The keyword lookups of the metadata records answer rows, not joins (#1477).

A keyword filter joins the record's keyword relation, and the filters
generated from ``Meta.fields`` carry no ``distinct=True``, so a record
which carried TWO keywords matching one lookup value appeared TWICE in
the queryset - twice on the page and twice in every facet count the api
answers over the same filtered queryset. The behave feature
``list_datasetmetadata_keyword_multiplicity.feature`` confirmed the shape
through the endpoint; what this module pins is the same answer on the
FILTER SIDE, for all three record classes behind the one mixin:

* one record, two matching keywords -> one row, for all three lookups
  the records expose (exact, icontains, contains);
* DISTINCT deduplicates records, not matches: two records which match
  through different keywords still answer twice;
* a non-matching value stays an empty answer (the flag must not turn
  the join into a constant).
"""
from django.test import TestCase

from registry.filters.metadata import (
    ApplicationMetadataRecordSpatialFilterSet,
    DatasetMetadataRecordSpatialFilterSet,
    ServiceMetadataRecordSpatialFilterSet)
from registry.models.metadata import (ApplicationMetadataRecord,
                                      DatasetMetadataRecord, Keyword,
                                      MetadataContact,
                                      ServiceMetadataRecord)

MATCHING_VALUE = 'niederschlag'  # matches both keywords, icontains and contains
SECOND_ONLY = 'iederschlagsdefizit'  # case sensitive, matches the second only


class KeywordLookupMultiplicityTests(TestCase):
    """One record, two matching keywords, one answer per lookup (#1477)."""

    @classmethod
    def setUpTestData(cls):
        cls.contact = MetadataContact.objects.create(
            name='Keyword distinct contact')
        cls.word_one = Keyword.objects.create(keyword='Niederschlag')
        cls.word_two = Keyword.objects.create(
            keyword='Niederschlagsdefizit')

    def record(self, model):
        """A fresh record of ``model`` carrying both keywords."""
        contacts = {'metadata_contact': self.contact}
        companion = {
            DatasetMetadataRecord: 'dataset_contact',
            ApplicationMetadataRecord: 'application_contact',
        }.get(model)
        if companion is not None:
            contacts[companion] = self.contact
        record = model.objects.create(
            title='Niederschlag und Niederschlagsdefizit', **contacts)
        record.keywords.set([self.word_one, self.word_two])
        return record

    def filter(self, filterset_class, model, param, value):
        return filterset_class(
            data={param: value},
            queryset=model.objects.all()).qs

    def test_two_matching_keywords_answer_one_row_per_lookup(self):
        for model, filterset_class in (
                (DatasetMetadataRecord,
                 DatasetMetadataRecordSpatialFilterSet),
                (ServiceMetadataRecord,
                 ServiceMetadataRecordSpatialFilterSet),
                (ApplicationMetadataRecord,
                 ApplicationMetadataRecordSpatialFilterSet)):
            with self.subTest(model=model.__name__):
                record = self.record(model)
                for param, value in (
                        ('keywords__keyword', 'Niederschlag'),
                        ('keywords__keyword__icontains', MATCHING_VALUE),
                        ('keywords__keyword__contains', SECOND_ONLY)):
                    answer = self.filter(
                        filterset_class, model, param, value)
                    self.assertEqual(
                        answer.count(), 1,
                        f'{param} answered the joined rows instead of the '
                        'record - the lookup lost its DISTINCT')
                    self.assertEqual(
                        [r.pk for r in answer], [record.pk])

    def test_distinct_deduplicates_records_not_matches(self):
        """Two records matching through different keywords still answer 2.

        The DISTINCT is about the record a join repeats, not about the
        keyword which matched - dropping a second RECORD would turn the
        facet into a different question.
        """
        both = self.record(DatasetMetadataRecord)
        second = DatasetMetadataRecord.objects.create(
            title='Niederschlagsdefizit separat',
            metadata_contact=self.contact,
            dataset_contact=self.contact)
        second.keywords.set([self.word_two])

        answer = self.filter(
            DatasetMetadataRecordSpatialFilterSet, DatasetMetadataRecord,
            'keywords__keyword__icontains', MATCHING_VALUE)
        self.assertEqual(
            sorted(pk for pk in answer.values_list('pk', flat=True)),
            sorted([both.pk, second.pk]),
            'a second record which matches through the shared keyword was '
            'distincted away')

    def test_a_value_matching_no_keyword_still_answers_nothing(self):
        self.record(DatasetMetadataRecord)
        answer = self.filter(
            DatasetMetadataRecordSpatialFilterSet, DatasetMetadataRecord,
            'keywords__keyword__icontains', 'Gletschereis')
        self.assertEqual(
            answer.count(), 0,
            'the keyword filter answered the whole table for no match')
