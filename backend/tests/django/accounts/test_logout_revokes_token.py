"""Pins that logging out revokes the credential server-side (#832).

The frontend's ``logout`` used to only drop its local copy of the knox token,
so a token which had been copied out of ``localStorage`` - through XSS, a
shared browser or leaked JS state - kept full access until its implicit TTL
expired. The endpoint which answers that gap exists since forever: ``MrMap/urls.py``
routes ``api/auth/logout`` to ``accounts.views.auth.LogoutView``, a knox
``LogoutView`` whose ``post`` deletes ``request._auth`` - the very
``AuthToken`` row the presented header hashes to.

What these tests hold:

* the token works before the logout, answers 401 after it, and the row behind
  it is gone, i.e. the revocation is a delete and not a status flag,
* the logout revokes **the presented token only** - knox's single-token view,
  not ``LogoutWithAllDevicesView`` - so a second device keeps working,
* the endpoint speaks ``POST``: knox's view implements no ``delete``, so a
  ``DELETE`` is answered with 405 and revokes nothing. The frontend has to
  match that verb.
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from knox.models import AuthToken

LOGOUT_URL = "/api/auth/logout"
WHOAMI_URL = "/api/accounts/who-am-i/"


class LogoutRevokesTokenTests(TestCase):
    """One user, one token, the two endpoints which share it."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="logout-probe", password="not-a-secret-pw1")
        # knox returns the full key only alongside the created row.
        self.token, self.key = AuthToken.objects.create(self.user)
        self.client = Client()

    def auth(self, key=None):
        return {"HTTP_AUTHORIZATION": f"Token {key or self.key}"}

    def test_the_token_answers_before_the_logout(self):
        """Precondition of everything below: the credential is live."""
        response = self.client.get(WHOAMI_URL, **self.auth())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.user.username)

    def test_logout_deletes_the_presented_token_row(self):
        response = self.client.post(LOGOUT_URL, **self.auth())

        self.assertEqual(response.status_code, 204)
        self.assertFalse(AuthToken.objects.filter(pk=self.token.pk).exists())

    def test_the_revoked_token_answers_the_denial_of_an_unknown_one(self):
        """The revoked credential is answered exactly like a never existing one.

        mrmap denies an unauthenticated request with **403**, not 401: DRF only
        keeps the 401 of ``AuthenticationFailed`` when the *first* configured
        authenticator of the view answers ``WWW-Authenticate``
        (``APIView.get_authenticate_header``), and ``DEFAULT_AUTHENTICATION_CLASSES``
        starts with ``SessionAuthentication``, which has none. What the revocation
        has to achieve - the copied token gets no access anymore and gives no
        hint that it once had some - is pinned by that equality.
        """
        self.client.post(LOGOUT_URL, **self.auth())

        revoked = self.client.get(WHOAMI_URL, **self.auth())
        unknown = self.client.get(WHOAMI_URL, **self.auth("a" * 32))

        self.assertEqual(revoked.status_code, unknown.status_code)
        self.assertIn(revoked.status_code, (401, 403))

    def test_logout_revokes_the_presented_token_only(self):
        """A second device of the same user keeps its credential."""
        other_token, other_key = AuthToken.objects.create(self.user)

        self.client.post(LOGOUT_URL, **self.auth())

        self.assertFalse(AuthToken.objects.filter(pk=self.token.pk).exists())
        self.assertTrue(AuthToken.objects.filter(pk=other_token.pk).exists())
        self.assertEqual(
            self.client.get(WHOAMI_URL, **self.auth(other_key)).status_code,
            200)

    def test_the_endpoint_speaks_post(self):
        """``DELETE`` is not a verb of knox's view and revokes nothing.

        The issue text of #832 suggests a ``DELETE``; this is the check which
        keeps that from being implemented against a view that would answer it
        with 405 while leaving the token alive.
        """
        response = self.client.delete(LOGOUT_URL, **self.auth())

        self.assertEqual(response.status_code, 405)
        self.assertTrue(AuthToken.objects.filter(pk=self.token.pk).exists())

    def test_anonymous_logout_changes_nothing(self):
        """Without a credential there is nothing to revoke: 401, no side effect."""
        response = self.client.post(LOGOUT_URL)

        self.assertEqual(response.status_code, 401)
        self.assertTrue(AuthToken.objects.filter(pk=self.token.pk).exists())
