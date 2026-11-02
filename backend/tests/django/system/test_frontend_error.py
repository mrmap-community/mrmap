import json
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from system.views import FrontendErrorView


class FrontendErrorBeaconTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.settings_patch = patch('system.views.settings')
        patched_settings = self.settings_patch.start()
        self.logger = patched_settings.ROOT_LOGGER
        self.addCleanup(self.settings_patch.stop)

    def _post(self, payload):
        request = self.factory.post(
            '/api/system/error',
            data=json.dumps(payload),
            content_type='application/json')
        return FrontendErrorView.as_view()(request)

    def test_reports_are_logged_without_authentication(self):
        response = self._post({
            'source': 'error',
            'message': 'boom',
            'stack': 'Error: boom\n  at x',
            'page': 'http://localhost/harvesting/jobs/1',
        })
        self.assertEqual(response.status_code, 204)
        self.logger.warning.assert_called_once()
        kwargs = self.logger.warning.call_args.kwargs
        self.assertIn('Frontend Error: boom', kwargs['msg'])
        frontend = kwargs['extra']['structured_data']['metaSDID@Frontend']
        self.assertEqual(frontend['source'], 'error')
        self.assertEqual(frontend['msg'], 'boom')
        self.assertIn('at x', frontend['stack'])
        self.assertEqual(
            frontend['page'], 'http://localhost/harvesting/jobs/1')

    def test_oversized_fields_are_truncated(self):
        self._post({'message': 'x' * 5000, 'stack': 'y' * 50000})
        kwargs = self.logger.warning.call_args.kwargs
        frontend = kwargs['extra']['structured_data']['metaSDID@Frontend']
        self.assertEqual(len(frontend['msg']), 1000)
        self.assertEqual(len(frontend['stack']), 4000)
        self.assertEqual(len(kwargs['msg']), len('Frontend Error: ') + 200)

    def test_missing_payload_still_logs_a_bare_report(self):
        response = self._post({})
        self.assertEqual(response.status_code, 204)
        kwargs = self.logger.warning.call_args.kwargs
        frontend = kwargs['extra']['structured_data']['metaSDID@Frontend']
        self.assertEqual(frontend['source'], 'error')
        self.assertEqual(frontend['msg'], 'unspecified frontend error')
