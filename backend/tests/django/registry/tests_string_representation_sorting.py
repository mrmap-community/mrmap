"""The list endpoints answer the sort on their display string.

The generic pickers of the frontend render resources with their
``string_representation`` and send exactly that field as ``sort`` - and the
drf-jsonapi `OrderingFilter` answers every sort field outside the viewset's
whitelist with a 400, which left these lists rendered empty. The viewsets now
whitelist the field and annotate the queryset so the database orders by the
same string the serializer answers (issue #1035).

A field which is not on that whitelist must still be answered with a 400, so
these tests pin the contract in both directions.
"""
from datetime import datetime, timedelta, timezone

from django.test import TestCase
from django.urls import reverse
from registry.enums.harvesting import HarvestingPhaseEnum
from registry.models.harvest import HarvestingJob
from registry.models.metadata import Keyword, MetadataContact, TimeExtent
from registry.models.service import CatalogueService

JSONAPI = "application/vnd.api+json"


class StringRepresentationSortTest(TestCase):
    """``sort=stringRepresentation`` orders the rows by the display string.

    The endpoint camelizes its field names, so the parameter arrives as
    ``stringRepresentation`` while the annotation is spelled
    ``string_representation`` - both spellings are asked for here, because
    the api has to answer both.
    """

    def _document(self, name, **query):
        """The json:api document the list endpoint answers to the query

        Args:
            name: the view name of the list endpoint
            **query: the query parameters of the request

        Returns:
            dict: the answered document
        """
        response = self.client.get(reverse(name), query, HTTP_ACCEPT=JSONAPI)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def _assert_sorted(self, name, queryset, **query):
        """The page answers the row ids in the order of the queryset

        Args:
            name: the view name of the list endpoint
            queryset: the rows in the expected order, ids
        """
        expected = [str(pk) for pk, in queryset.values_list("pk")[:10]]
        document = self._document(name, **query)
        self.assertEqual([row["id"] for row in document["data"]], expected)


class KeywordSortTest(StringRepresentationSortTest):
    """The keyword list sorts by the keyword itself - its display string"""

    @classmethod
    def setUpTestData(cls):
        cls.zebra = Keyword.objects.create(keyword="Zebra")
        cls.alpha = Keyword.objects.create(keyword="alpha")
        cls.brown = Keyword.objects.create(keyword="Brown")

    def test_sort_ascending_answers_the_keywords_in_alphabetic_order(self):
        for sort in ("stringRepresentation", "string_representation"):
            with self.subTest(sort=sort):
                self._assert_sorted(
                    "registry:keyword-list",
                    Keyword.objects.order_by("keyword"),
                    **{"sort": sort})

    def test_sort_descending_answers_the_last_keyword_first(self):
        self._assert_sorted(
            "registry:keyword-list",
            Keyword.objects.order_by("-keyword"),
            **{"sort": "-stringRepresentation"})

    def test_an_unknown_sort_is_still_rejected(self):
        response = self.client.get(
            reverse("registry:keyword-list"),
            {"sort": "not_a_field"}, HTTP_ACCEPT=JSONAPI)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["errors"][0]["code"], "invalid")


class TimeExtentSortTest(StringRepresentationSortTest):
    """The time extent list sorts by the display string of the extent.

    ``TimeExtent.__str__`` answers the begin of a single value, the
    ``begin;end;resolution`` triple of an interval and the currently open
    window of a rolling extent - the annotation of the viewset orders
    exactly these strings.
    """

    @classmethod
    def setUpTestData(cls):
        cls.early = TimeExtent.objects.create(
            begin=datetime(2020, 1, 1, tzinfo=timezone.utc),
            end=datetime(2020, 1, 1, tzinfo=timezone.utc))
        cls.late = TimeExtent.objects.create(
            begin=datetime(2021, 6, 1, tzinfo=timezone.utc),
            end=datetime(2021, 9, 1, tzinfo=timezone.utc),
            resolution=timedelta(days=1))
        cls.rolling = TimeExtent.objects.create(
            begin=None, end=None, is_relative=True, resolution=timedelta(days=3))

    def test_sort_ascending_answers_the_extents_in_display_order(self):
        for sort in ("stringRepresentation", "string_representation"):
            with self.subTest(sort=sort):
                self._assert_sorted(
                    "registry:timeextent-list",
                    TimeExtent.objects.with_string_representation()
                    .order_by("string_representation"),
                    **{"sort": sort})

    def test_the_single_value_with_the_earlier_begin_comes_first(self):
        """The display strings begin with their begin, so 2020 precedes 2021

        A rolling extent renders the now, so with the two fixed dates of this
        test it is the last one on an ascending page - today is after 2021.
        """
        document = self._document(
            "registry:timeextent-list", **{"sort": "stringRepresentation"})
        self.assertEqual(
            [str(self.early.pk), str(self.late.pk), str(self.rolling.pk)],
            [row["id"] for row in document["data"]])

    def test_sort_descending_answers_the_last_extent_first(self):
        document = self._document(
            "registry:timeextent-list", **{"sort": "-stringRepresentation"})
        self.assertEqual(
            [str(self.rolling.pk), str(self.late.pk), str(self.early.pk)],
            [row["id"] for row in document["data"]])

    def test_an_unknown_sort_is_still_rejected(self):
        response = self.client.get(
            reverse("registry:timeextent-list"),
            {"sort": "not_a_field"}, HTTP_ACCEPT=JSONAPI)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["errors"][0]["code"], "invalid")


class HarvestingJobSortTest(StringRepresentationSortTest):
    """The harvesting job list sorts by the display string of the job.

    ``HarvestingJob.__str__`` names the catalogue of the run by its title and
    the run by its id - ``<catalogue title> (harvesting job <pk>)``, or just
    ``harvesting job <pk>`` for a file import without a catalogue - and the
    annotation mirrors both branches, so the sort orders the rows the way the
    rendered list reads (#1035, #1045).
    """

    @classmethod
    def setUpTestData(cls):
        contact = MetadataContact.objects.create(name="Sort contact")
        cls.catalogue = CatalogueService(
            id='33333333-3333-3333-3333-333333333333',
            title="Alpha catalogue", version=202, origin=1,
            service_url="https://example.com/csw",
            metadata_contact=contact, service_contact=contact)
        CatalogueService.objects.bulk_create([cls.catalogue])
        cls.with_catalogue = HarvestingJob(service=cls.catalogue)
        cls.without_catalogue = [
            HarvestingJob(
                phase=HarvestingPhaseEnum.DOWNLOAD_RECORDS.value)
            for _ in range(3)]
        HarvestingJob.objects.bulk_create(
            [cls.with_catalogue, *cls.without_catalogue])

    def test_sort_ascending_answers_the_jobs_in_display_order(self):
        for sort in ("stringRepresentation", "string_representation"):
            with self.subTest(sort=sort):
                self._assert_sorted(
                    "registry:harvestingjob-list",
                    HarvestingJob.objects.with_string_representation()
                    .order_by("string_representation"),
                    **{"sort": sort})

    def test_sort_descending_answers_the_last_job_first(self):
        self._assert_sorted(
            "registry:harvestingjob-list",
            HarvestingJob.objects.with_string_representation()
            .order_by("-string_representation"),
            **{"sort": "-stringRepresentation"})

    def test_the_annotation_answers_what_the_model_string_answers(self):
        """Every annotated value is the plain ``str`` of its job - with a
        catalogue as well as without one"""
        for job in HarvestingJob.objects.with_string_representation():
            self.assertEqual(str(job.string_representation), str(job))

    def test_the_join_over_the_catalogue_keeps_the_file_imports(self):
        """A job which names no catalogue is no loser of the annotation: the
        file imports must be ordered and rendered like the catalogue runs, so
        the join over the catalogue is a left join and not a filter (#1045)"""
        annotated = HarvestingJob.objects.with_string_representation()
        self.assertEqual(
            {job.pk for job in annotated},
            set(HarvestingJob.objects.values_list("pk", flat=True)))
        self.assertIsNotNone(
            annotated.get(pk=self.without_catalogue[0].pk)
            .string_representation)

    def test_an_unknown_sort_is_still_rejected(self):
        response = self.client.get(
            reverse("registry:harvestingjob-list"),
            {"sort": "not_a_field"}, HTTP_ACCEPT=JSONAPI)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["errors"][0]["code"], "invalid")
