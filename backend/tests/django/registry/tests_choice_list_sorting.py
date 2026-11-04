"""The choice based lists answer the sort a generic list client must send.

A generic list page always sends a `sort` with its first request and the
drf-jsonapi `OrderingFilter` answers every sort field outside the viewset's
whitelist with a 400 - which leaves such a list rendered empty. The choice
based resources have neither an `id` nor a date to sort by, so their views
annotate the `id` of the json:api resource with the natural key of the choice
and whitelist that key, the id and the label - the same shape the wms
operations endpoint already used (issue #943).

A field which is not on that whitelist must still be answered with a 400, so
these tests pin the contract in both directions.
"""
from django.test import TestCase
from django.urls import reverse
from registry.models.metadata import IsoCategory, Language
from registry.models.security import WebFeatureServiceOperation

JSONAPI = "application/vnd.api+json"

#: the choice based list endpoints with their model and view name
CHOICE_LISTS = (
    ("registry:language-list", Language),
    ("registry:isocategory-list", IsoCategory),
    ("registry:wfsoperation-list", WebFeatureServiceOperation),
)


class ChoiceListSortTest(TestCase):
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

    def test_sort_by_id_answers_the_rows_in_order(self):
        """`sort=id` and `sort=-id` answer the page in the order of the key"""
        for name, model in CHOICE_LISTS:
            for sort in ("id", "value"):
                with self.subTest(endpoint=name, sort=sort):
                    document = self._document(name, **{"sort": sort})
                    expected = [str(value) for value in model.objects
                                .order_by("value").values_list("value", flat=True)][:10]
                    self.assertEqual([row["id"] for row in document["data"]], expected)

    def test_sort_by_id_descending_answers_the_last_key_first(self):
        for name, model in CHOICE_LISTS:
            with self.subTest(endpoint=name, sort="-id"):
                document = self._document(name, **{"sort": "-id"})
                expected = [str(value) for value in model.objects
                            .order_by("-value").values_list("value", flat=True)][:10]
                self.assertEqual([row["id"] for row in document["data"]], expected)

    def test_sort_by_label_answers_the_rows_in_label_order(self):
        """The annotated label of the choices is sortable as well"""
        for name, model in CHOICE_LISTS:
            with self.subTest(endpoint=name, sort="label"):
                document = self._document(name, **{"sort": "label"})
                expected = [str(value) for value in model.objects
                            .with_label().order_by("label")
                            .values_list("value", flat=True)][:10]
                self.assertEqual([row["id"] for row in document["data"]], expected)

    def test_a_sort_the_resource_does_not_have_is_still_rejected(self):
        """The whitelist stays a whitelist: an unknown field answers 400

        These lists have no `created_at` and no `name` - the frontend which
        guesses a sort has to reach for one of the whitelisted fields, and a
        field outside the whitelist must not be sorted by silently.
        """
        for name, _model in CHOICE_LISTS:
            for sort in ("created_at", "name", "unknown"):
                with self.subTest(endpoint=name, sort=sort):
                    response = self.client.get(
                        reverse(name), {"sort": sort}, HTTP_ACCEPT=JSONAPI)
                    self.assertEqual(response.status_code, 400, response.content)
                    self.assertEqual(response.json()["errors"][0]["code"], "invalid")

    def test_the_list_without_a_sort_answers_its_rows(self):
        for name, model in CHOICE_LISTS:
            with self.subTest(endpoint=name):
                document = self._document(name)
                self.assertGreater(document["meta"]["pagination"]["count"], 0)
                self.assertEqual(
                    [row["id"] for row in document["data"]],
                    [str(value) for value in model.objects
                     .order_by("value").values_list("value", flat=True)][:10])
