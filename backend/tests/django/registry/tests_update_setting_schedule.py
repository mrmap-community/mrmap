from datetime import datetime, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase
from django_celery_beat.models import CrontabSchedule
from registry.models.update import WebMapServiceUpdateSetting
from registry.serializers.update import WebMapServiceUpdateSettingSerializer


class UpdateSettingScheduleTest(SimpleTestCase):
    def setting(self, **kwargs):
        created = datetime(2026, 9, 30, 8, 1, 25, tzinfo=timezone.utc)
        values = dict(
            id=1, last_run_at=created, date_changed=created, enabled=True,
            crontab=CrontabSchedule(
                id=1, minute='*/5', hour='*', day_of_week='*',
                day_of_month='*', month_of_year='*', timezone=ZoneInfo('UTC'),
            ),
        )
        values.update(kwargs)
        setting = WebMapServiceUpdateSetting(**values)
        return setting

    def test_next_run_is_anchored_to_last_dispatch_not_today(self):
        self.assertEqual(
            self.setting().next_run_expected_at,
            datetime(2026, 9, 30, 8, 5, tzinfo=timezone.utc),
        )

    def test_disabled_setting_has_no_expected_run(self):
        self.assertIsNone(self.setting(enabled=False).next_run_expected_at)

    def test_never_run_setting_uses_last_change(self):
        self.assertEqual(
            self.setting(last_run_at=None).next_run_expected_at,
            datetime(2026, 9, 30, 8, 5, tzinfo=timezone.utc),
        )

    def test_last_change_does_not_override_last_dispatch(self):
        changed = datetime(2026, 10, 1, 8, 11, tzinfo=timezone.utc)
        self.assertEqual(
            self.setting(date_changed=changed).next_run_expected_at,
            datetime(2026, 9, 30, 8, 5, tzinfo=timezone.utc),
        )

    def test_future_start_time_is_respected(self):
        start = datetime(2026, 10, 2, 8, 11, tzinfo=timezone.utc)
        self.assertEqual(
            self.setting(start_time=start).next_run_expected_at,
            datetime(2026, 10, 2, 8, 15, tzinfo=timezone.utc),
        )

    def test_cron_timezone_and_daylight_saving_transition(self):
        setting = self.setting(
            last_run_at=datetime(2026, 10, 24, 9, tzinfo=timezone.utc),
            date_changed=datetime(2026, 10, 24, 9, tzinfo=timezone.utc),
            crontab=CrontabSchedule(
                id=1, minute='0', hour='10', day_of_week='*',
                day_of_month='*', month_of_year='*', timezone=ZoneInfo('Europe/Berlin'),
            ),
        )
        self.assertEqual(
            setting.next_run_expected_at.astimezone(timezone.utc),
            datetime(2026, 10, 25, 9, tzinfo=timezone.utc),
        )

    def test_overdue_only_after_next_scheduled_dispatch(self):
        setting = self.setting()
        serializer = WebMapServiceUpdateSettingSerializer()
        for minute, expected in [(4, False), (5, False), (6, True)]:
            with self.subTest(minute=minute), patch(
                'registry.serializers.update.timezone.now',
                return_value=datetime(2026, 9, 30, 8, minute, tzinfo=timezone.utc),
            ):
                self.assertEqual(serializer.get_run_overdue(setting), expected)

    def test_recent_dispatch_moves_the_expected_run_forward(self):
        setting = self.setting(last_run_at=datetime(2026, 9, 30, 8, 5, tzinfo=timezone.utc))
        self.assertEqual(setting.next_run_expected_at, datetime(2026, 9, 30, 8, 10, tzinfo=timezone.utc))
        with patch('registry.serializers.update.timezone.now', return_value=datetime(2026, 9, 30, 8, 6, tzinfo=timezone.utc)):
            self.assertFalse(WebMapServiceUpdateSettingSerializer().get_run_overdue(setting))

    def test_existing_results_do_not_hide_a_missed_dispatch(self):
        setting = self.setting()
        setting.has_update_jobs = True
        setting.has_monitoring_runs = True
        with patch('registry.serializers.update.timezone.now', return_value=datetime(2026, 10, 1, tzinfo=timezone.utc)):
            self.assertTrue(WebMapServiceUpdateSettingSerializer().get_run_overdue(setting))

    def test_completed_one_off_task_is_not_overdue(self):
        self.assertIsNone(self.setting(one_off=True, total_run_count=1).next_run_expected_at)

    def test_expired_task_is_not_overdue(self):
        setting = self.setting(expires=datetime(2026, 9, 30, 8, 2, tzinfo=timezone.utc))
        with patch('registry.serializers.update.timezone.now', return_value=datetime(2026, 10, 1, tzinfo=timezone.utc)):
            self.assertFalse(WebMapServiceUpdateSettingSerializer().get_run_overdue(setting))

    def test_last_run_is_read_only_and_creation_field_is_removed(self):
        fields = WebMapServiceUpdateSettingSerializer().fields
        self.assertTrue(fields['last_run_at'].read_only)
        self.assertNotIn('created_at', fields)
