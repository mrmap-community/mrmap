"""The gate of the rfc5424 formatter: a file only for records with detail (#1033).

The formatter used to store the structured data of every record the syslog
handler formatted as one json file below the media root. On a running
deployment that pile was dominated by Celery's per task INFO and repeating
warnings rather than by the slow request diagnostics the dumps exist for. The
formatter now writes only for records which carry detail beyond the code
position it adds itself, and the syslog line carries the pointer to the dump
only when the file was actually written.

The file work is asserted against a temporary media root, like the sweep tests:
the formatter reads ``MEDIA_ROOT`` while it runs, so an
``override_settings(MEDIA_ROOT=...)`` reaches it.
"""

import json
import logging
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase

from system.logging.formatter import (RFC5424Formatter,
                                      SLOW_REQUEST_DUMP_SUBDIR)

LOGGER = logging.getLogger("tests.system.logging")

STRATEGY_PATH = ("/opt/venv/lib/python3.15/site-packages"
                 "/celery/worker/strategy.py")


def build_record(msg="Task received", level=logging.INFO,
                 extra=None, exc_info=None):
    """One record as the syslogged loggers emit it, with the extras under test."""
    return LOGGER.makeRecord(
        "celery.worker.strategy", level, STRATEGY_PATH, 161,
        msg, (), exc_info, func="task_message_handler", extra=extra)


class RFC5424FormatterDumpTests(SimpleTestCase):
    """What the formatter writes below the media root and what it leaves alone."""

    def setUp(self):
        media_root = tempfile.TemporaryDirectory()
        self.addCleanup(media_root.cleanup)
        self.media_root = Path(media_root.name)
        self.dumps = self.media_root / SLOW_REQUEST_DUMP_SUBDIR
        override = self.settings(MEDIA_ROOT=str(self.media_root))
        override.enable()
        self.addCleanup(override.disable)

    def format(self, record):
        return RFC5424Formatter().format(record)

    def written_dumps(self):
        if not self.dumps.exists():
            return []
        return sorted(name.name for name in self.dumps.glob("*.json"))

    def assertNoDump(self, line):
        """The line stands alone: no file, no directory, no dangling pointer."""
        self.assertEqual(self.written_dumps(), [])
        self.assertFalse(
            self.dumps.exists(),
            "a record without detail may not even create the dump directory")
        self.assertNotIn("metaSDID@Details", line)

    def test_an_ordinary_record_writes_no_file_and_carries_no_pointer(self):
        """Celery's per task INFO is answered by its line, not by a file.

        This was the dominant writer: on the measured deployment one file per
        such record piled up below the media root (#1033).
        """
        line = self.format(build_record())

        self.assertNoDump(line)
        self.assertTrue(line.endswith("- - Task received"), line)

    def test_suppressing_the_python_meta_alone_does_not_write_a_file(self):
        """The gate asks for detail, not for the absence of the python meta."""
        line = self.format(build_record(extra={"disable_python_meta": True}))

        self.assertNoDump(line)

    def test_a_record_with_request_detail_is_dumped_and_pointed_at(self):
        """A slow request record is what the dumps are there for."""
        structured_data = {
            "metaSDID@request": {
                "path": "http://testserver/api/registry/csw",
                "duration_ms": 450,
                "status_code": 200,
                "method": "GET",
            },
        }
        record = build_record(
            msg="Slow Request Detected", level=logging.WARNING,
            extra={"disable_python_meta": True,
                   "structured_data": structured_data})

        line = self.format(record)

        written = self.written_dumps()
        self.assertEqual(len(written), 1)
        pointer = (f'[metaSDID@Details json="{settings.MEDIA_URL}'
                   f'{SLOW_REQUEST_DUMP_SUBDIR}/{written[0]}"]')
        self.assertIn(pointer, line)
        self.assertEqual(json.loads((self.dumps / written[0]).read_text()),
                         structured_data)

    def test_the_dump_carries_the_python_meta_the_formatter_adds(self):
        """The file keeps the whole structured data, including the added meta."""
        record = build_record(
            extra={"structured_data": {"metaSDID@message": {"msg": "detail"}}})

        self.format(record)

        written = self.written_dumps()
        self.assertEqual(len(written), 1)
        dumped = json.loads((self.dumps / written[0]).read_text())
        self.assertEqual(dumped["metaSDID@message"], {"msg": "detail"})
        self.assertEqual(dumped["metaSDID@python"], {
            "module": "strategy",
            "pathname": STRATEGY_PATH,
            "lineno": 161,
            "funcName": "task_message_handler",
        })

    def test_an_exception_record_is_dumped_for_its_traceback(self):
        """A traceback is verbose detail which the syslog line does not carry."""
        try:
            raise ValueError("boom")
        except ValueError:
            # makeRecord hands exc_info on unfilled, as _log would have resolved it
            record = build_record(msg="Task failed", level=logging.ERROR,
                                  exc_info=sys.exc_info())

        line = self.format(record)

        written = self.written_dumps()
        self.assertEqual(len(written), 1)
        self.assertIn("metaSDID@Details", line)
        dumped = json.loads((self.dumps / written[0]).read_text())
        self.assertIn("ValueError: boom",
                      dumped["metaSDID@exception"]["traceback"])

    def test_a_failed_write_leaves_the_line_without_a_pointer(self):
        """A pointer is answered only for a dump which was actually written."""
        record = build_record(
            extra={"structured_data": {"metaSDID@request": {"path": "x"}}})

        with patch("builtins.open", side_effect=OSError("disk full")):
            line = self.format(record)

        self.assertEqual(self.written_dumps(), [])
        self.assertNotIn("metaSDID@Details", line)
        self.assertIn("Task received", line)
