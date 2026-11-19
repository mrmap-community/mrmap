"""``POST /api/accounts/users`` must create a user who can log in (#1451).

The audit of #1439 found the create path byte-broken: ``UserCreateSerializer``
ran the plain ``ModelSerializer.save`` - which INSERTs the raw password like
any other model value - and only hashed onto the in-memory instance after
that. Consequences: a plaintext credential at rest, and ``check_password``
never matching the stored value, so an API-created user could NEVER log in.
Nothing tested this endpoint before, which is how it survived.

The fix hashes before the single save; these are the two acceptance
assertions the issue names, plus the parts of the old payload shape
(``groups``) and the refusal of a passwordless document that the fix must
not regress. The write itself is pinned from the side of the database: the
raw value may never appear in a statement and the user table may be written
exactly once, and a password which breaks the configured
``AUTH_PASSWORD_VALIDATORS`` is refused on its field before any write.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import identify_hasher
from django.contrib.auth.models import Group
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APIClient

JSONAPI = "application/vnd.api+json"

RAW_PASSWORD = "Kr4ft-Voll-Text-Passw0rt"


def user_document(username, password, groups=None):
    """A JSON:API write document of the create serializer's payload."""
    data = {
        "type": "User",
        "attributes": {"username": username, "password": password},
        "relationships": {
            "groups": {"data": [
                {"type": "Group", "id": str(group.pk)}
                for group in (groups or [])
            ]}
        }
    }
    return {"data": data}


class UserCreateAPITest(TestCase):
    """the endpoint, its stored rows and the login its users must survive"""

    def setUp(self):
        self.superuser = get_user_model().objects.create_superuser(
            username="creator", password="x")
        self.api = APIClient()
        self.url = reverse("accounts:user-list")

    def _create(self, document):
        self.api.force_authenticate(user=self.superuser)
        return self.api.post(
            self.url, document, format="vnd.api+json",
            HTTP_ACCEPT=JSONAPI)

    def test_the_stored_password_is_a_hash_and_never_the_document_value(
            self):
        response = self._create(user_document("newcomer", RAW_PASSWORD))
        self.assertEqual(response.status_code, 201, response.content)
        stored = get_user_model().objects.get(
            username="newcomer").password
        self.assertNotEqual(stored, RAW_PASSWORD)
        self.assertNotIn(RAW_PASSWORD, stored)
        # a real hasher, not a hand-made string: identify_hasher only
        # resolves values a Django hasher actually produced
        identify_hasher(stored)

    def test_an_api_created_user_can_log_in(self):
        """the login of the issue's acceptance, through the model backend"""
        response = self._create(user_document("newcomer", RAW_PASSWORD))
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(self.client.login(
            username="newcomer", password=RAW_PASSWORD))

    def test_the_groups_of_the_document_are_applied(self):
        group = Group.objects.create(name="api group")
        response = self._create(user_document(
            "grouped", RAW_PASSWORD, groups=[group]))
        self.assertEqual(response.status_code, 201, response.content)
        self.assertIn(
            group,
            get_user_model().objects.get(username="grouped").groups.all())

    def test_a_document_without_a_password_is_refused(self):
        document = user_document("nameless", RAW_PASSWORD)
        document["data"]["attributes"].pop("password")
        response = self._create(document)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(
            get_user_model().objects.filter(username="nameless").exists())

    def test_a_password_broken_by_the_policy_is_refused_on_its_field(self):
        """A policy-violating password answers 400, not a server error.

        ``set_password`` remembers the raw value and ``AbstractBaseUser.save``
        runs the configured AUTH_PASSWORD_VALIDATORS over it - *after* the
        INSERT, without ATOMIC_REQUESTS behind an already-written row. The
        serializer validates the same policy first, so this is the 400 of a
        rejected field and nothing is written (#1451).
        """
        response = self._create(user_document("weakling", "short"))
        self.assertEqual(response.status_code, 400, response.content)
        # the refusal names the password - not, say, the required groups
        # relation, whose absence answers the same status for any body
        self.assertIn(
            "/data/attributes/password",
            [error["source"]["pointer"] for error in response.data])
        self.assertFalse(
            get_user_model().objects.filter(username="weakling").exists())

    def test_the_answer_never_repeats_the_password(self):
        response = self._create(user_document("newcomer", RAW_PASSWORD))
        self.assertEqual(response.status_code, 201, response.content)
        self.assertNotIn(RAW_PASSWORD, response.content.decode())

    def test_the_raw_password_reaches_no_query_and_the_row_is_written_once(
            self):
        """The write plan of the creation, read from the statements.

        Capturing what the request executed is what makes "hashed before
        the single save" assertable: the raw value appears in no statement
        and exactly one INSERT reaches the user table.
        """
        with CaptureQueriesContext(connection) as queries:
            response = self._create(user_document("newcomer", RAW_PASSWORD))
        self.assertEqual(response.status_code, 201, response.content)
        self.assertFalse(
            [query for query in queries.captured_queries
             if RAW_PASSWORD in query["sql"]],
            "the raw password was carried by a query: "
            f"{[q['sql'] for q in queries.captured_queries]}")
        inserts = [query["sql"] for query in queries.captured_queries
                   if query["sql"].lstrip().upper().startswith("INSERT")
                   and '"accounts_user"' in query["sql"]]
        self.assertEqual(len(inserts), 1, inserts)
