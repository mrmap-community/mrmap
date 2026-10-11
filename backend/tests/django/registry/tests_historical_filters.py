from datetime import timedelta
from uuid import uuid4

from django.db.models import F
from django.test import TestCase
from django.utils import timezone
from registry.models.metadata import MetadataContact
from registry.querys.historical import with_delta_size
from registry.serializers.historical import HistorySerializerMixin
from registry.views.historical import (
    CatalogueServiceHistoricalViewSet, FeatureTypeHistoricalViewSet,
    LayerHistoricalViewSet, WebFeatureServiceHistoricalViewSet,
    WebMapServiceHistoricalViewSet)
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory


class HistoricalFiltersTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.model = WebMapServiceHistoricalViewSet.queryset.model
        cls.object_id = uuid4()
        cls.start = timezone.now() - timedelta(days=1)
        values = {
            "id": cls.object_id,
            "history_relation_id": cls.object_id,
            "history_type": "+",
            "title": "Original title",
            "abstract": "",
            "origin": 1,
            "version": 130,
            "service_url": "https://example.com/wms",
        }
        cls.records = []
        changes = [
            {},
            # Neither history metadata nor non-editable fields count.
            {"history_type": "~", "history_change_reason": "unchanged",
             "version": 111},
            {"title": "Changed title", "fees": "Description",
             "is_active": True},
            {"fees": None, "service_contact_id": 123},
            {"service_contact_id": None},
        ]
        for index, changeset in enumerate(changes):
            values.update(changeset)
            cls.records.append(cls.model.objects.create(
                **values, history_date=cls.start + timedelta(minutes=index),
            ))
        # Existing relation filters validate against the live service table.
        # Bulk creation avoids creating an extra history entry via signals.
        contact = MetadataContact.objects.create(name="Test contact")
        service_model = cls.model.instance_type
        service_model.objects.bulk_create([
            service_model(
                id=cls.object_id, title="Original title", origin=1,
                version=130, service_url="https://example.com/wms",
                metadata_contact=contact, service_contact=contact,
            ),
        ])
        other_id = uuid4()
        cls.other = cls.model.objects.create(
            **{**values, "id": other_id, "history_relation_id": other_id},
            history_date=cls.start + timedelta(minutes=10),
        )

    def view(self, params=None, view_class=WebMapServiceHistoricalViewSet):
        view = view_class()
        if view.queryset.model is self.model:
            # Proxy tests can leave audit records after deleting live services.
            # Keep these assertions scoped to both objects created by this class.
            view.queryset = view.queryset.filter(
                id__in=[self.object_id, self.other.id],
            )
        view.request = Request(APIRequestFactory().get("/", params or {}))
        view.action = "list"
        return view

    def filtered(self, params):
        view = self.view(params)
        return view.filter_queryset(view.get_queryset())

    def test_sql_size_matches_serializer_delta(self):
        qs = (self.view().get_queryset()
              .select_related(None).prefetch_related(None))
        qs = with_delta_size(qs).annotate(delta_size=F("_delta_size"))
        serializer = HistorySerializerMixin()
        for record in qs:
            record.prev_prefetched_record = record.prev_record
            delta = serializer.get_delta(record)
            self.assertEqual(
                record.delta_size, None if delta is None else len(delta),
            )
        self.assertEqual(
            dict(qs.values_list("history_id", "delta_size")),
            {**dict(zip([r.pk for r in self.records], [None, 0, 3, 2, 1])),
             self.other.pk: None},
        )

    def test_jsonapi_greater_than_filter_is_lazy_and_uses_one_query(self):
        with self.assertNumQueries(0):
            qs = self.filtered({"filter[deltaSize.gt]": "2"})
        with self.assertNumQueries(1):
            self.assertEqual(list(qs.values_list("pk", flat=True)),
                             [self.records[2].pk])

    def test_zero_threshold_excludes_null_and_empty_deltas(self):
        self.assertSetEqual(
            set(self.filtered({"filter[deltaSize.gt]": "0"})
                .values_list("pk", flat=True)),
            {r.pk for r in self.records[2:]},
        )

    def test_changed_or_created_includes_creation_and_changes(self):
        with self.assertNumQueries(0):
            qs = self.filtered({"filter[changedOrCreated]": "true"})
        with self.assertNumQueries(1):
            self.assertSetEqual(
                set(qs.values_list("pk", flat=True)),
                {self.records[0].pk, *(r.pk for r in self.records[2:])},
            )

    def test_changed_or_created_false_disables_filter(self):
        qs = self.filtered({"filter[changedOrCreated]": "false"})
        self.assertNotIn("_delta_size", qs.query.annotations)
        self.assertEqual(qs.count(), len(self.records) + 1)

    def test_changed_or_created_composes_with_other_filters(self):
        # Give another object a creation record to check OR cannot bypass
        # the historyRelation constraint.
        self.model.objects.filter(pk=self.other.pk).update(history_type="+")
        qs = self.filtered({
            "filter[changedOrCreated]": "true",
            "filter[historyRelation]": str(self.object_id),
        })
        self.assertSetEqual(
            set(qs.values_list("pk", flat=True)),
            {self.records[0].pk, *(r.pk for r in self.records[2:])},
        )
        narrowed = self.filtered({
            "filter[changedOrCreated]": "true",
            "filter[deltaSize.gt]": "2",
        })
        self.assertEqual(list(narrowed.values_list("pk", flat=True)),
                         [self.records[2].pk])

    def test_changed_or_created_filters_before_pagination(self):
        view = self.view({
            "filter[changedOrCreated]": "true",
            "page[size]": "1",
            "sort": "historyDate",
        })
        page = view.paginate_queryset(
            view.filter_queryset(view.get_queryset()))
        self.assertEqual(view.paginator.page.paginator.count, 4)
        self.assertEqual(len(page), 1)
        self.assertEqual(page[0].pk, self.records[0].pk)
        self.assertIsNone(page[0].prev_prefetched_record)

    def test_none_filter_only_matches_missing_predecessors(self):
        self.assertSetEqual(
            set(self.filtered({"filter[delta]": "None"})
                .values_list("pk", flat=True)),
            {self.records[0].pk, self.other.pk},
        )

    def test_outer_filters_do_not_hide_predecessor(self):
        start = self.records[2].history_date.isoformat()
        qs = self.filtered({
            "filter[deltaSize.gt]": "2",
            "filter[historyRelation]": str(self.object_id),
            "filter[historyDate.gte]": start,
        })
        self.assertEqual(list(qs.values_list("pk", flat=True)),
                         [self.records[2].pk])

    def test_equal_timestamps_are_not_predecessors(self):
        first = self.records[0]
        first.pk = uuid4()
        first.title = "Another record at the first timestamp"
        first.save(force_insert=True)
        self.assertTrue(self.filtered({"filter[delta]": "None"})
                        .filter(pk=first.pk).exists())

    def test_filtering_precedes_pagination_and_preserves_prefetch(self):
        view = self.view({"filter[deltaSize.gt]": "0", "page[size]": "1"})
        page = view.paginate_queryset(
            view.filter_queryset(view.get_queryset()))
        self.assertEqual(view.paginator.page.paginator.count, 3)
        self.assertEqual(len(page), 1)
        self.assertEqual(page[0].pk, self.records[4].pk)
        self.assertEqual(page[0].prev_prefetched_record.pk, self.records[3].pk)
        with self.assertNumQueries(0):
            self.assertEqual(
                len(HistorySerializerMixin().get_delta(page[0])), 1)

    def test_invalid_values_are_rejected(self):
        for params in [
            {"filter[deltaSize.gt]": "invalid"},
            {"filter[deltaSize.gt]": "-1"},
            {"filter[delta]": "[]"},
        ]:
            with self.subTest(params=params):
                with self.assertRaises(ValidationError):
                    self.filtered(params)

    def test_omitted_filter_does_not_add_delta_size_expression(self):
        self.assertNotIn("_delta_size", self.filtered({}).query.annotations)

    def test_all_historical_viewsets_accept_filter(self):
        for view_class in [
            WebMapServiceHistoricalViewSet, LayerHistoricalViewSet,
            WebFeatureServiceHistoricalViewSet, FeatureTypeHistoricalViewSet,
            CatalogueServiceHistoricalViewSet,
        ]:
            with self.subTest(view=view_class.__name__):
                for params in [
                    {"filter[deltaSize.gt]": "0"},
                    {"filter[changedOrCreated]": "true"},
                ]:
                    view = self.view(params, view_class)
                    qs = view.filter_queryset(view.get_queryset())
                    self.assertIn("IS DISTINCT FROM", str(qs.query))
        layer_view = self.view({"filter[service]": str(self.object_id)},
                               LayerHistoricalViewSet)
        qs = layer_view.filter_queryset(layer_view.get_queryset())
        self.assertIn(str(self.object_id).replace("-", ""),
                      str(qs.query).replace("-", ""))


class LayerChangeTypeFiltersTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.model = LayerHistoricalViewSet.queryset.model
        cls.start = timezone.now() - timedelta(days=1)
        cls.records = {}
        layer_id = uuid4()
        values = dict(id=layer_id, title="Original", service_id=uuid4(),
                      mptt_lft=1, mptt_rgt=2, mptt_depth=0,
                      history_change_reason="updatejob_id: 2")
        for index, (name, changes) in enumerate([
            ("added", {"history_type": "~"}),
            ("unchanged", {}),
            ("modified", {"title": "Changed"}),
            ("removed", {"history_type": "-"}),
            ("created", {"id": uuid4(), "history_type": "+"}),
            ("deleted_without_predecessor", {"id": uuid4(), "history_type": "-"}),
        ]):
            values.update(changes)
            values["history_relation_id"] = values["id"]
            cls.records[name] = cls.model.objects.create(
                **values, history_date=cls.start + timedelta(minutes=index))

    def view(self, change_type):
        view = LayerHistoricalViewSet()
        view.queryset = view.queryset.filter(pk__in=[r.pk for r in self.records.values()])
        view.request = Request(APIRequestFactory().get("/", {
            "filter[changeType]": change_type,
            "filter[historyChangeReason]": "updatejob_id: 2",
            "page[size]": "1",
        }))
        view.action = "list"
        return view

    def test_categories_are_disjoint_and_use_one_query(self):
        expected = {"added": ["added", "created"], "modified": ["modified"],
                    "unchanged": ["unchanged"],
                    "removed": ["removed", "deleted_without_predecessor"]}
        for change_type, names in expected.items():
            with self.subTest(change_type=change_type):
                view = self.view(change_type)
                with self.assertNumQueries(0):
                    qs = view.filter_queryset(view.get_queryset())
                with self.assertNumQueries(1):
                    self.assertSetEqual(set(qs.values_list("pk", flat=True)),
                                        {self.records[name].pk for name in names})

    def test_filter_runs_before_pagination(self):
        view = self.view("added")
        page = view.paginate_queryset(view.filter_queryset(view.get_queryset()))
        self.assertEqual(view.paginator.page.paginator.count, 2)
        self.assertEqual(len(page), 1)

    def test_invalid_category_is_rejected(self):
        view = self.view("invalid")
        with self.assertRaises(ValidationError):
            view.filter_queryset(view.get_queryset())

    def test_change_reason_remains_scoped(self):
        record = self.records["modified"]
        self.model.objects.filter(pk=record.pk).update(history_change_reason="updatejob_id: 3")
        view = self.view("modified")
        self.assertFalse(view.filter_queryset(view.get_queryset()).exists())
