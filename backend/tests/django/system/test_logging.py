from datetime import timedelta
from unittest.mock import patch

from django.db import DatabaseError, connection
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from system.logging.middleware import LogSlowRequestsMiddleware
from system.logging.util import interpolate_sql


@override_settings(LOG_LONG_RUNNING_REQUEST_THRESHOLD_MS=400)
class SlowRequestLoggingTests(TestCase):
    def setUp(self):
        self.request = RequestFactory().get('/api/registry/csw')
        self.response = HttpResponse(status=200)
        self.logger_patch = patch('system.logging.middleware.logger')
        self.logger = self.logger_patch.start()
        self.addCleanup(self.logger_patch.stop)
        self.interpolate_patch = patch(
            'system.logging.middleware.interpolate_sql', wraps=interpolate_sql)
        self.interpolate = self.interpolate_patch.start()
        self.addCleanup(self.interpolate_patch.stop)

    def test_fast_requests_do_not_interpolate_or_log(self):
        def get_response(request):
            with connection.cursor() as cursor:
                cursor.execute('SELECT %s', [1])
            self.interpolate.assert_not_called()
            return self.response

        middleware = LogSlowRequestsMiddleware(get_response)
        for duration in (100, 400):
            with self.subTest(duration=duration), patch.object(
                    middleware, 'get_duration_ms', side_effect=[12, duration]):
                self.assertIs(middleware(self.request), self.response)
            self.interpolate.assert_not_called()
            self.logger.warning.assert_not_called()

    def test_slow_requests_keep_query_order_parameters_and_durations(self):
        def get_response(request):
            params = [7, 'two  spaces']
            with connection.cursor() as cursor:
                cursor.execute('select %s,\n\t%s', params)
                params[0] = 8
                cursor.execute('SELECT %s', params[:1])
            self.interpolate.assert_not_called()
            return self.response

        middleware = LogSlowRequestsMiddleware(get_response)
        with patch.object(middleware, 'get_duration_ms', side_effect=[12, 23, 450]):
            self.assertIs(middleware(self.request), self.response)

        self.assertEqual(self.interpolate.call_count, 2)
        self.logger.warning.assert_called_once()
        logged = self.logger.warning.call_args.kwargs
        self.assertEqual(logged['msg'], 'Slow Request Detected')
        self.assertTrue(logged['extra']['disable_python_meta'])
        self.assertEqual(logged['extra']['structured_data'], {
            'metaSDID@message': {'msg': 'Slow Request Detected'},
            'metaSDID@request': {
                'path': 'http://testserver/api/registry/csw',
                'duration_ms': 450,
                'status_code': 200,
                'method': 'GET',
            },
            'metaSDID@queries': {
                '1_sql': "select 7,  'two  spaces'",
                '1_duration_ms': 12,
                '2_sql': 'SELECT 8',
                '2_duration_ms': 23,
            },
        })

    def test_named_parameters_are_captured_before_they_are_reused(self):
        def get_response(request):
            params = {'value': 42}
            with connection.cursor() as cursor:
                cursor.execute('SELECT %(value)s', params)
            params['value'] = 99
            return self.response

        middleware = LogSlowRequestsMiddleware(get_response)
        with patch.object(middleware, 'get_duration_ms', side_effect=[12, 450]):
            middleware(self.request)
        queries = self.logger.warning.call_args.kwargs['extra']['structured_data']['metaSDID@queries']
        self.assertEqual(queries['1_sql'], 'SELECT 42')

    def test_interpolation_does_not_inflate_recorded_durations(self):
        start = timezone.now()

        def get_response(request):
            with connection.cursor() as cursor:
                cursor.execute('SELECT %s', [1])
            now.return_value += timedelta(milliseconds=450)
            return self.response

        def interpolate(sql, params):
            now.return_value += timedelta(seconds=1)
            return interpolate_sql(sql, params)

        with patch('system.logging.middleware.timezone.now', return_value=start) as now:
            self.interpolate.side_effect = interpolate
            LogSlowRequestsMiddleware(get_response)(self.request)

        data = self.logger.warning.call_args.kwargs['extra']['structured_data']
        self.assertEqual(data['metaSDID@request']['duration_ms'], 450)
        self.assertEqual(data['metaSDID@queries']['1_duration_ms'], 0)

    def test_overlapping_requests_keep_their_own_start_time(self):
        start = timezone.now()

        def get_response(request):
            if request.path == '/outer':
                now.return_value += timedelta(milliseconds=200)
                middleware(RequestFactory().get('/inner'))
                now.return_value += timedelta(milliseconds=100)
            else:
                now.return_value += timedelta(milliseconds=300)
            return self.response

        middleware = LogSlowRequestsMiddleware(get_response)
        with patch('system.logging.middleware.timezone.now', return_value=start) as now:
            middleware(RequestFactory().get('/outer'))
        self.logger.warning.assert_called_once()
        data = self.logger.warning.call_args.kwargs['extra']['structured_data']
        self.assertEqual(data['metaSDID@request']['path'], 'http://testserver/outer')
        self.assertEqual(data['metaSDID@request']['duration_ms'], 600)

    def test_failed_queries_are_still_logged_when_the_view_handles_them(self):
        def get_response(request):
            with self.assertRaises(DatabaseError), connection.cursor() as cursor:
                cursor.execute('SELECT 1 / %s', [0])
            return HttpResponse(status=500)

        middleware = LogSlowRequestsMiddleware(get_response)
        with patch.object(middleware, 'get_duration_ms', side_effect=[12, 450]):
            self.assertEqual(middleware(self.request).status_code, 500)
        data = self.logger.warning.call_args.kwargs['extra']['structured_data']
        self.assertEqual(data['metaSDID@request']['status_code'], 500)
        self.assertEqual(data['metaSDID@queries'], {
            '1_sql': 'SELECT 1 / 0', '1_duration_ms': 12,
        })

    def test_slow_requests_without_queries_still_log_request_metadata(self):
        middleware = LogSlowRequestsMiddleware(lambda request: self.response)
        with patch.object(middleware, 'get_duration_ms', return_value=450):
            middleware(self.request)
        self.interpolate.assert_not_called()
        data = self.logger.warning.call_args.kwargs['extra']['structured_data']
        self.assertEqual(data['metaSDID@request']['duration_ms'], 450)
        self.assertNotIn('metaSDID@queries', data)


class InterpolateSqlTests(SimpleTestCase):
    def test_interpolates_without_parsing_or_reformatting_sql(self):
        sql = 'select %s, %s, %s'
        with patch('sqlparse.format') as format_sql:
            self.assertEqual(interpolate_sql(sql, [1, 'two  spaces', None]),
                             "select 1, 'two  spaces', None")
        format_sql.assert_not_called()

    def test_preserves_sql_without_parameters(self):
        sql = 'select 1,  2'
        self.assertEqual(interpolate_sql(sql, None), sql)
        self.assertEqual(interpolate_sql(sql, []), sql)

    def test_interpolates_positional_and_named_parameters(self):
        self.assertEqual(interpolate_sql('select %s', (42,)), 'select 42')
        self.assertEqual(interpolate_sql('select %(value)s', {'value': 42}), 'select 42')

    def test_invalid_placeholders_keep_sql_and_diagnostics(self):
        for sql, params in [('SELECT %s, %s', [1]),
                            ('SELECT %(missing)s', {'value': 1}),
                            ('SELECT %q', [1])]:
            with self.subTest(sql=sql):
                self.assertTrue(interpolate_sql(sql, params).startswith(
                    f'{sql} -- [Interpolation failed: '))
