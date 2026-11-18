"""The user a client creates through the API can log in (#1451).

``UserCreateSerializer`` let the generic ``ModelSerializer`` INSERT the
password column with the raw request value and hashed only the in-memory
instance afterwards: the row at rest held the plaintext credential and
``check_password`` never matched it again, so an API-created user could
never log in. Nothing tested ``POST /api/accounts/users`` before. These
tests walk the call a client makes and ask exactly the questions the
issue names: the row holds a hash of the password, the write happened
once, no query ever carried the raw value, and ``client.login()``
succeeds with it.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import is_password_usable
from django.contrib.auth.models import Group
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

JSONAPI = "application/vnd.api+json"
PASSWORD = "TestPassw0rt99"


def user_document(username, password, group=None):
    """A JSON:API creation document for a ``User``.

    The ``groups`` member is always present: the create serializer declares
    the relation explicitly, and a declared relation keeps DRF's own
    ``required=True`` instead of the model's ``blank=True`` - an existing
    contract of the endpoint, so even the smallest valid call answers the
    relationship, with an empty set when it names no group.
    """
    data = {
        "type": "User",
        "attributes": {"username": username, "password": password},
        "relationships": {"groups": {"data": [
            {"type": "Group", "id": str(group.pk)}] if group else []}},
    }
    return {"data": data}


class UserCreateAPITestCase(TestCase):
    """``POST /api/accounts/users`` as a client sends it.

    The actor is a superuser: the viewset answers behind
    ``DjangoObjectPermissions``, so the create needs ``accounts.add_user``
    just like any deployment's administrator account.
    """

    def setUp(self):
        self.root = get_user_model().objects.create_superuser(
            username="root", password="x")
        self.api = APIClient()
        self.api.force_authenticate(self.root)

    def create_user(self, username="newcomer", password=PASSWORD, group=None):
        """The POST of the creation document, with the queries it ran.

        Capturing the statements is what makes "hashed before the single
        save" assertable: the raw value may not appear in any of them,
        and exactly one INSERT reaches the user table.
        """
        with CaptureQueriesContext(connection) as queries:
            response = self.api.post(
                "/api/accounts/users",
                data=user_document(username, password, group),
                format="vnd.api+json",
                HTTP_ACCEPT=JSONAPI)
        return response, queries

    def test_created_user_can_login(self):
        """The login of the created user is the issue's acceptance test."""
        response, _ = self.create_user()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(self.client.login(
            username="newcomer", password=PASSWORD))

    def test_password_is_stored_as_a_hash(self):
        response, _ = self.create_user()
        self.assertEqual(response.status_code, 201, response.data)
        user = get_user_model().objects.get(username="newcomer")
        self.assertNotEqual(user.password, PASSWORD)
        self.assertTrue(is_password_usable(user.password))
        self.assertTrue(user.check_password(PASSWORD))

    def test_raw_password_reaches_no_query_and_the_user_is_written_once(self):
        response, queries = self.create_user()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertFalse(
            [query for query in queries.captured_queries
             if PASSWORD in query["sql"]],
            "the raw password was carried by a query: "
            f"{[q['sql'] for q in queries.captured_queries]}")
        inserts = [query["sql"] for query in queries.captured_queries
                   if query["sql"].lstrip().upper().startswith("INSERT")
                   and '"accounts_user"' in query["sql"]]
        self.assertEqual(len(inserts), 1, inserts)

    def test_answer_does_not_repeat_the_password(self):
        """The answer names the new user but never repeats the credential."""
        response, _ = self.create_user()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertNotIn(PASSWORD, response.content.decode())

    def test_groups_join_the_created_user(self):
        """The writable ``groups`` relation survives the custom create."""
        group = Group.objects.create(name="API Crew")
        response, _ = self.create_user(group=group)
        self.assertEqual(response.status_code, 201, response.data)
        user = get_user_model().objects.get(username="newcomer")
        self.assertIn(group, user.groups.all())

    def test_a_password_of_the_policy_answers_400(self):
        """A password the configured validators refuse is a client error.

        ``set_password`` followed by the save lets Django run
        AUTH_PASSWORD_VALIDATORS on the write; the serializer validates
        first so this answers 400 and creates nothing instead of failing
        in the save (#1451).
        """
        response, queries = self.create_user(password="short")
        self.assertEqual(response.status_code, 400, response.data)
        # the refusal names the password - not, say, the required groups
        # relation, whose absence would answer the same status for any body
        self.assertIn(
            "/data/attributes/password",
            [error["source"]["pointer"] for error in response.data])
        self.assertFalse(
            get_user_model().objects.filter(username="newcomer").exists())
        self.assertFalse(
            [query for query in queries.captured_queries
             if '"accounts_user"' in query["sql"]
             and query["sql"].lstrip().upper().startswith("INSERT")])
