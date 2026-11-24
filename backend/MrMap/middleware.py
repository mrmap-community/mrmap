"""Middleware which answers the project's own security headers.

The header values live in ``MrMap/settings.py`` next to the rest of the
production-gated HTTP hygiene (#1473, audit SEC-17); this module only answers
them, which is what keeps the decisions testable without a middleware stack.
"""

from django.conf import settings


class ContentSecurityPolicyMiddleware:
    """Answer ``Content-Security-Policy`` of every backend response.

    Django has no setting for this header, and the policy is a deployment
    value of the same family as the ``SECURE_*`` block, so it is decided in
    settings (``_content_security_policy_from_env``) and answered here.
    ``SecurityMiddleware`` deliberately does not own it, which is why this is
    listed *above* it: a middleware only sees what the ones below return, and
    ``SecurityMiddleware`` answers its 301 of ``SECURE_SSL_REDIRECT`` from
    inside its own request phase. Listed below it, this middleware would never
    see that redirect - nor the 400 of the host validation, the answers where
    a forged ``X-Forwarded-Host`` or a stored ``http://`` reference shows up.

    An empty setting turns the header off (the knob of a deployment which
    needs none), and an already-set header wins, so a reverse proxy or a
    view which answers its own stricter policy is never overwritten.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        policy = getattr(settings, "CONTENT_SECURITY_POLICY", "")
        if policy and not response.headers.get("Content-Security-Policy"):
            response.headers["Content-Security-Policy"] = policy
        return response
