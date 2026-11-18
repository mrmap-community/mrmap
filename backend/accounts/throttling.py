"""The login attempt throttle of the credential endpoints (#1450).

``POST /api/auth/session`` and ``POST /api/auth/login`` are the two endpoints
where the application reads a password. Until #1450 they read it as often as a
caller cared to send it: DRF shipped no throttle rates at all, so a credential
guessing tool ran unthrottled against the one anonymous, password-carrying
surface of the API.

Two things make the straightforward ``throttle_classes`` answer wrong here,
and this module is the answer to both:

* **DRF checks throttles after authenticating.** ``InitialHandler.initial()``
  runs ``perform_authentication()`` before ``check_throttles()``, and
  ``Request._authenticate()`` re-raises an authenticator's refusal - a wrong
  password ends the request in the authentication step, and the throttle check
  that would count it is never reached. A throttle installed the standard way
  on these views counts *successful* logins only. ``ThrottleLoginAttemptsMixin``
  runs the check before the request's credentials are looked at, so every
  attempt counts, right or wrong.
* **The caller of a refused attempt is anonymous.** ``AnonRateThrottle`` keys
  the rate on the client address but lets an authenticated request pass
  uncounted, and ``UserRateThrottle`` cannot count an attempt whose credential
  resolved to nobody. What a flood is here is *attempts from one address*,
  right or wrong, which is what ``LoginAttemptThrottle`` counts.

Like every DRF throttle the count lives in the default cache - the Redis of
the deployment - so all application processes share one budget per address.
"""
from django.core.exceptions import ImproperlyConfigured
from rest_framework import throttling
from rest_framework.settings import api_settings


class LoginAttemptThrottle(throttling.SimpleRateThrottle):
    """Requests per client address to the credential endpoints (#1450).

    Deliberately not ``AnonRateThrottle``: that class skips authenticated
    requests, and an authenticated POST to ``api/auth/session`` is a *re-login*
    - it carries the password again and belongs in the budget exactly like the
    anonymous first login. Every POST counts; the verbs of these endpoints
    which carry no password - the session probe, the logout - neither count
    nor cost.
    """

    scope = "login"

    def get_rate(self):
        """The configured rate, read when the attempt arrives.

        The base class binds ``THROTTLE_RATES`` to the settings *at import
        time*, which silently freezes whatever was configured then; reading the
        live settings answers the operators who set the rate after the workers
        imported the module - and fails loudly when a settings change drops
        the scope this throttle is declared with, instead of throttling
        nothing.
        """
        try:
            return api_settings.DEFAULT_THROTTLE_RATES[self.scope]
        except KeyError:
            raise ImproperlyConfigured(
                f"LOGIN throttle scope '{self.scope}' has no rate; set "
                f'REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["{self.scope}"].')

    def get_cache_key(self, request, view):
        """The budget of this client, or ``None`` for a verb without a credential.

        ``None`` answers ``allow_request`` with "yes" *without* recording the
        request: only the credential-carrying verb pays into the budget.
        """
        if request.method != "POST":
            return None
        ident = self.get_login_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}

    def get_login_ident(self, request):
        """The client whose attempts this is.

        Behind the frontend's nginx every request arrives from one container
        address, so DRF's ``REMOTE_ADDR`` would pool a whole deployment into a
        single budget - and that pooling is a denial of service, one caller
        exhausting the logins of everyone. The conf of the frontend therefore
        sends ``X-Real-IP: $remote_addr``: nginx *replaces* a header of that
        name rather than passing a client's word for it, so it is the client
        the edge saw. Where no edge stood in front - a direct call of the
        backend in development, the test client - the peer address decides, as
        it always has. A caller who can set headers on a direct connection
        sets its own budget; that connection is the developer's own.
        """
        return (request.META.get("HTTP_X_REAL_IP")
                or request.META.get("REMOTE_ADDR")
                or "unknown")


class ThrottleLoginAttemptsMixin:
    """Runs the view's throttles before its authentication (#1450).

    Applied to the credential endpoints only; a view without
    ``throttle_classes`` passes through untouched. DRF's own
    ``check_throttles`` of the same request is dropped, so an attempt is
    counted once, not twice - see the module docstring for why the standard
    position counts nothing that matters here.
    """

    def perform_authentication(self, request):
        for throttle in self.get_throttles():
            if not throttle.allow_request(request, self):
                self.throttled(request, throttle.wait())
        super().perform_authentication(request)

    def check_throttles(self, request):
        """DRF's post-authentication check - already done, above."""
