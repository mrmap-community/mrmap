from django.test import TestCase
from mptt2.models import Tree
from registry.models.service import FeatureType, Layer, WebFeatureService, WebMapService
from registry.views.service import (
    FeatureTypeViewSet, LayerViewSet, WebFeatureServiceViewSet,
    WebMapServiceViewSet,
)
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory


class UpdateCandidatesTest(TestCase):
    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json", "test_wfs.json"]

    def service_pairs(self):
        return [
            (WebMapService, Layer, WebMapServiceViewSet, LayerViewSet),
            (WebFeatureService, FeatureType, WebFeatureServiceViewSet,
             FeatureTypeViewSet),
        ]

    def create_candidate(self, model):
        service = model.objects.filter(update_candidate_of__isnull=True).first()
        candidate = model.objects.create(
            title="Update candidate", service_url=service.service_url,
            version=service.version, origin=service.origin,
            update_candidate_of=service,
            metadata_contact=service.metadata_contact,
            service_contact=service.service_contact,
        )
        return service, candidate

    def create_element(self, model, service, title):
        values = {"service": service, "title": title}
        if model is Layer:
            values.update(mptt_tree=Tree.objects.create(), mptt_lft=1,
                          mptt_rgt=2, mptt_depth=0)
        else:
            values["default_reference_system"] = FeatureType.objects.first().default_reference_system
        return model.objects.create(**values)

    def filtered_ids(self, view_class, value):
        params = {} if value is None else {"filter[isUpdateCandidate]": value}
        view = view_class()
        view.request = Request(APIRequestFactory().get("/", params))
        view.action = "list"
        view.args = ()
        view.kwargs = {}
        return set(view.filter_queryset(view.get_queryset()).values_list("pk", flat=True))

    def test_service_and_element_filters(self):
        for model, child_model, service_view, child_view in self.service_pairs():
            with self.subTest(model=model.__name__):
                service, candidate = self.create_candidate(model)
                published_child = self.create_element(child_model, service, "Published")
                candidate_child = self.create_element(child_model, candidate, "Candidate")
                for view, published, temporary in [
                    (service_view, service, candidate),
                    (child_view, published_child, candidate_child),
                ]:
                    self.assertIn(published.pk, self.filtered_ids(view, "false"))
                    self.assertNotIn(temporary.pk, self.filtered_ids(view, "false"))
                    self.assertIn(temporary.pk, self.filtered_ids(view, "true"))
                    self.assertNotIn(published.pk, self.filtered_ids(view, "true"))
                    self.assertIn(temporary.pk, self.filtered_ids(view, None))

    def test_candidates_do_not_create_history_on_save_or_cascade_delete(self):
        for model, child_model, _, _ in self.service_pairs():
            with self.subTest(model=model.__name__):
                service, candidate = self.create_candidate(model)
                child = self.create_element(child_model, candidate, "Candidate")
                candidate_id, child_id = candidate.pk, child.pk
                candidate.title = "Updated candidate"
                candidate.save()
                child.title = "Updated child"
                child.save()
                self.assertFalse(model.change_log.filter(id=candidate_id).exists())
                self.assertFalse(child_model.change_log.filter(id=child_id).exists())
                # Exercise QuerySet deletion as used by update-job cleanup.
                model.objects.filter(pk=candidate_id).delete()
                self.assertFalse(model.change_log.filter(id=candidate_id).exists())
                self.assertFalse(child_model.change_log.filter(id=child_id).exists())
                before = model.change_log.filter(id=service.pk).count()
                service.title = "Published change"
                service.save()
                self.assertEqual(model.change_log.filter(id=service.pk).count(), before + 1)

    def test_promoted_elements_start_history_when_published(self):
        for model, child_model, _, _ in self.service_pairs():
            with self.subTest(model=model.__name__):
                service, candidate = self.create_candidate(model)
                child = self.create_element(child_model, candidate, "New element")
                child.service = service
                child.save()
                self.assertEqual(child_model.change_log.filter(id=child.pk).count(), 1)
                child_id = child.pk
                child_model.objects.filter(pk=child_id).delete()
                self.assertTrue(child_model.change_log.filter(id=child_id, history_type="-").exists())
