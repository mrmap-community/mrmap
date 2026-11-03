import decimal
import uuid
from datetime import date, datetime, timedelta
from datetime import timezone as python_timezone
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
            # the literal of the type, not the repr of the value: a bare None is a
            # column name to postgres, NULL is the parameter it was (#887)
            self.assertEqual(interpolate_sql(sql, [1, 'two  spaces', None]),
                             "select 1, 'two  spaces', NULL")
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

    def test_a_type_without_an_adapter_falls_back_on_repr(self):
        """A value the driver cannot quote is still worth reading in the dump."""
        class Opaque:
            def __repr__(self):
                return '<opaque>'

        self.assertEqual(interpolate_sql('select %s', [Opaque()]),
                         'select <opaque>')


class InterpolatedSqlRunsTests(TestCase):
    """The statement of a dump is the statement the database was asked with (#887).

    A dump is worth what an analyzer can do with it, so the interpolated statement
    has to answer the same rows as the parameterized one when it is run without its
    parameters. None of the types below did while they were rendered with ``repr``:
    ``datetime.timedelta(0)`` answers ``ERROR: schema "datetime" does not exist``,
    which is a false friend worth more than the time it costs - it sent the reporter
    looking for an aggregation which was never there.
    """

    def assert_interpolated_statement_answers_the_same(self, sql, params):
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            asked = cursor.fetchall()

        interpolated = interpolate_sql(sql, params)
        self.assertNotIn('%s', interpolated, interpolated)
        self.assertNotIn('%(', interpolated, interpolated)

        with connection.cursor() as cursor:
            cursor.execute(interpolated)
            self.assertEqual(cursor.fetchall(), asked, interpolated)

    def test_the_types_of_a_dump_interpolate_to_executable_literals(self):
        job = 'beeacc4e-55fe-4dd0-b5f5-23b1e20eed87'
        for sql, params in (
                ('SELECT %s::uuid', [uuid.UUID(job)]),
                ('SELECT COALESCE(%s::interval, \'0 seconds\'::interval)',
                 [timedelta(0)]),
                ('SELECT COALESCE(%s::interval, \'0 seconds\'::interval)',
                 [timedelta(days=1, seconds=5400)]),
                ('SELECT %s::timestamptz',
                 [datetime(2026, 11, 2, 13, 4, tzinfo=python_timezone.utc)]),
                ('SELECT %s::date', [date(2026, 11, 2)]),
                ('SELECT %s::text', ["it's slow"]),
                ('SELECT %s::text', ['two  spaces']),
                ('SELECT %s::int', [7]),
                ('SELECT %s::numeric', [decimal.Decimal('1.5')]),
                ('SELECT %s::bool', [True]),
                ('SELECT %s::bytea', [b'ab'])):
            with self.subTest(sql=sql, params=repr(params)):
                self.assert_interpolated_statement_answers_the_same(sql, params)

    def test_named_parameters_interpolate_to_executable_literals(self):
        self.assert_interpolated_statement_answers_the_same(
            'SELECT %(job)s::uuid, %(since)s::timestamptz',
            {'job': uuid.UUID('beeacc4e-55fe-4dd0-b5f5-23b1e20eed87'),
             'since': datetime(2026, 11, 2, 13, 4, tzinfo=python_timezone.utc)})
