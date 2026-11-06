"""The user and organization lists answer the sort on their display string.

The generic pickers of the frontend render resources with their
``string_representation`` and send exactly that field as ``sort`` - and the
drf-jsonapi `OrderingFilter` answers every sort field outside the viewset's
whitelist with a 400, which left these lists rendered empty. The viewsets now
whitelist the field and annotate the queryset so the database orders by the
same string the serializer answers (issue #1035).

A field which is not on that whitelist must still be answered with a 400, so
these tests pin the contract in both directions.
"""
from django.contrib.auth import get_user_model
from django.db.models import F
from django.test import TestCase
from django.urls import reverse
from accounts.models.groups import Organization
from rest_framework.test import APIClient

JSONAPI = "application/vnd.api+json"
User = get_user_model()


class UserSortTest(TestCase):
    """``sort=stringRepresentation`` orders the users by ``User.__str__``"""

    @classmethod
    def setUpTestData(cls):
        # the four shapes of the display string: a full name, only the first
        # name, only the last name and no name at all
        cls.full = User.objects.create(
            username="carla", first_name="Carla", last_name="Coburg")
        cls.first = User.objects.create(username="bruno", first_name="Bruno")
        cls.last = User.objects.create(username="ada", last_name="Lovelace")
        cls.none = User.objects.create(username="zoe")
        # the list is guarded by object permissions, so it is asked as superuser
        cls.admin = User.objects.create_superuser(
            username="sortadmin", password="test")
        cls.api = APIClient()
        cls.api.force_authenticate(cls.admin)
        cls.api.credentials(HTTP_ACCEPT=JSONAPI)

    def _document(self, **query):
        response = self.api.get(
            reverse("accounts:user-list"), query, HTTP_ACCEPT=JSONAPI)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def _expected(self, sort):
        """The user ids in the order of the display string annotation"""
        return [str(pk) for pk in
                User.objects.with_string_representation()
                .order_by(sort).values_list("pk", flat=True)]

    def test_the_annotation_answers_the_string_of_the_model(self):
        """Every annotated value is the plain ``str`` of its user"""
        for user in User.objects.with_string_representation():
            self.assertEqual(str(user.string_representation), str(user))

    def test_sort_ascending_answers_the_users_in_display_order(self):
        for sort in ("stringRepresentation", "string_representation"):
            with self.subTest(sort=sort):
                document = self._document(**{"sort": sort})
                self.assertEqual(
                    [row["id"] for row in document["data"]],
                    self._expected("string_representation"))

    def test_sort_descending_answers_the_last_user_first(self):
        document = self._document(**{"sort": "-stringRepresentation"})
        self.assertEqual(
            [row["id"] for row in document["data"]],
            self._expected("-string_representation"))

    def test_the_existing_sort_fields_keep_working(self):
        """The whitelist replaced the implicit fields - it must not drop them"""
        document = self._document(**{"sort": "username"})
        self.assertEqual(
            [row["id"] for row in document["data"]],
            [str(pk) for pk in
             User.objects.order_by("username").values_list("pk", flat=True)])

    def test_an_unknown_sort_is_still_rejected(self):
        response = self.api.get(
            reverse("accounts:user-list"),
            {"sort": "not_a_field"}, HTTP_ACCEPT=JSONAPI)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["errors"][0]["code"], "invalid")


class OrganizationSortTest(TestCase):
    """``sort=stringRepresentation`` orders the organizations by their name"""

    @classmethod
    def setUpTestData(cls):
        cls.beta = Organization.objects.create(name="Beta Behörde")
        cls.alpha = Organization.objects.create(name="Alpha Amt")
        cls.gamma = Organization.objects.create(name="Gamma Gemeinde")

    def _document(self, **query):
        response = self.client.get(
            reverse("accounts:organization-list"), query, HTTP_ACCEPT=JSONAPI)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def _expected(self, order):
        """The organization ids in the name order the database answers

        The deployments bootstrap already carries organizations - the display
        string sort orders all of them, so the expectation reads them from the
        very column the annotation mirrors.
        """
        return [str(pk) for pk in
                Organization.objects.order_by(order)
                .values_list("pk", flat=True)]

    def test_the_display_string_is_the_name_of_the_organization(self):
        """The annotation of the view mirrors ``Organization.__str__``"""
        for organization in Organization.objects.annotate(
                string_representation=F("name")).order_by("pk"):
            self.assertEqual(organization.string_representation,
                             str(organization))

    def test_sort_ascending_answers_the_names_in_order(self):
        for sort in ("stringRepresentation", "string_representation"):
            with self.subTest(sort=sort):
                document = self._document(**{"sort": sort})
                self.assertEqual(
                    [row["id"] for row in document["data"]],
                    self._expected("name"))

    def test_sort_descending_answers_the_last_name_first(self):
        document = self._document(**{"sort": "-stringRepresentation"})
        self.assertEqual(
            [row["id"] for row in document["data"]],
            self._expected("-name"))

    def test_sort_by_the_model_field_the_string_mirrors_still_works(self):
        document = self._document(**{"sort": "name"})
        self.assertEqual(
            [row["id"] for row in document["data"]], self._expected("name"))

    def test_an_unknown_sort_is_still_rejected(self):
        response = self.client.get(
            reverse("accounts:organization-list"),
            {"sort": "not_a_field"}, HTTP_ACCEPT=JSONAPI)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["errors"][0]["code"], "invalid")
