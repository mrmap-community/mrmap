"""The local Vite frontend can use the backend's browser session."""

from corsheaders.middleware import CorsMiddleware
from django.conf import settings
from django.http import HttpResponse
from django.middleware.csrf import CsrfViewMiddleware
from django.test import RequestFactory, SimpleTestCase


class DevLoginSettingsTests(SimpleTestCase):
    def test_login_preflight_allows_credentials_from_vite(self):
        middleware = CorsMiddleware(lambda request: HttpResponse())
        for origin in ('http://localhost:5173', 'http://127.0.0.1:5173'):
            with self.subTest(origin=origin):
                request = RequestFactory().options(
                    '/api/auth/session', HTTP_ORIGIN=origin,
                    HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST',
                    HTTP_ACCESS_CONTROL_REQUEST_HEADERS='authorization,x-csrftoken')
                response = middleware(request)
                self.assertEqual(response['access-control-allow-origin'], origin)
                self.assertEqual(response['access-control-allow-credentials'], 'true')
                self.assertIn('authorization', response['access-control-allow-headers'])
                self.assertIn('x-csrftoken', response['access-control-allow-headers'])

    def test_unlisted_origin_cannot_read_session(self):
        request = RequestFactory().get(
            '/api/auth/session', HTTP_ORIGIN='https://untrusted.example')
        response = CorsMiddleware(lambda request: HttpResponse())(request)
        self.assertNotIn('access-control-allow-origin', response)

    def test_vite_origin_passes_csrf_origin_check(self):
        middleware = CsrfViewMiddleware(lambda request: HttpResponse())
        for origin in ('http://localhost:5173', 'http://127.0.0.1:5173'):
            with self.subTest(origin=origin):
                self.assertIn(origin, settings.CSRF_TRUSTED_ORIGINS)
                request = RequestFactory().post('/api/auth/session', HTTP_ORIGIN=origin)
                self.assertTrue(middleware._origin_verified(request))
