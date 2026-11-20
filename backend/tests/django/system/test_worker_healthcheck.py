"""The candidate keeps the directed broker round trip of inspect ping."""

import io
import subprocess
import sys
from contextlib import redirect_stderr
from unittest import TestCase
from unittest.mock import patch

from system import worker_healthcheck


class WorkerHealthcheckTests(TestCase):
    def setUp(self):
        factory = patch("system.worker_healthcheck.Celery")
        self.factory = factory.start()
        self.addCleanup(factory.stop)
        self.app = self.factory.return_value.__enter__.return_value
        self.connection = (
            self.app.connection_for_write.return_value.__enter__.return_value)
        self.inspect = self.app.control.inspect.return_value
        self.inspect.ping.return_value = {"celery@local": {"ok": "pong"}}

    def test_broker_configuration_and_directed_ping(self):
        with patch.dict("os.environ", {"REDIS_HOST": "broker", "REDIS_PORT": "6380"}):
            self.assertTrue(worker_healthcheck.ping("celery@local"))
        self.factory.assert_called_once_with(
            "healthcheck", broker="redis://broker:6380",
            fixups=[], set_as_current=False)
        self.connection.ensure_connection.assert_called_once_with(max_retries=0)
        self.app.control.inspect.assert_called_once_with(
            destination=["celery@local"], timeout=2, connection=self.connection)

    def test_missing_wrong_worker_and_bad_replies_are_unhealthy(self):
        for reply in (None, {}, {"celery@other": {"ok": "pong"}},
                      {"celery@local": {"error": "unavailable"}},
                      {"celery@local": {"ok": "unexpected"}}):
            with self.subTest(reply=reply):
                self.inspect.ping.return_value = reply
                self.assertFalse(worker_healthcheck.ping("celery@local"))

    def test_another_worker_cannot_hide_a_missing_local_worker(self):
        self.inspect.ping.return_value = {
            "celery@other": {"ok": "pong"}, "celery@local": None}
        self.assertFalse(worker_healthcheck.ping("celery@local"))

    def test_probe_uses_its_own_hostname(self):
        with patch("system.worker_healthcheck.socket.gethostname", return_value="local"):
            self.assertEqual(0, worker_healthcheck.main())
        self.app.control.inspect.assert_called_once_with(
            destination=["celery@local"], timeout=2, connection=self.connection)

    def test_broker_failure_exits_unhealthy_without_leaking_exception_text(self):
        self.connection.ensure_connection.side_effect = OSError("secret-url")
        output = io.StringIO()
        with redirect_stderr(output):
            self.assertEqual(1, worker_healthcheck.main())
        self.assertIn("OSError", output.getvalue())
        self.assertNotIn("secret-url", output.getvalue())

    def test_missing_reply_exits_unhealthy(self):
        self.inspect.ping.return_value = None
        with redirect_stderr(io.StringIO()):
            self.assertEqual(1, worker_healthcheck.main())

    def test_real_client_does_not_load_the_django_application(self):
        # A fresh interpreter catches accidental settings/task imports even
        # when this module runs after the Django suite has initialized them.
        subprocess.run([sys.executable, "-c", """
import sys
from unittest.mock import patch
from system.worker_healthcheck import ping
with patch('kombu.Connection.ensure_connection'), patch(
        'celery.app.control.Inspect.ping',
        return_value={'celery@local': {'ok': 'pong'}}):
    assert ping('celery@local')
assert 'django.db' not in sys.modules
assert not any(name.split('.')[0] in {'MrMap', 'registry'} for name in sys.modules)
"""], check=True, capture_output=True, text=True)
