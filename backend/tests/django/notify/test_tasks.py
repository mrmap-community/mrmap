from unittest.mock import patch

from django.test import TestCase
from notify.enums import ProcessStatusEnum
from notify.models import BackgroundProcess
from notify.tasks import BackgroundProcessBased, get_background_process


class BackgroundProcessTaskTests(TestCase):
    def setUp(self):
        self.process = BackgroundProcess.objects.create(
            process_type='registering', phase='queued', total_steps=4, done_steps=1)
        self.task = BackgroundProcessBased()
        self.task.background_process_pk = self.process.pk

    def info(self):
        return BackgroundProcess.objects.process_info().get(pk=self.process.pk)

    @patch('notify.tasks.post_save.send')
    def test_start_does_not_require_task_results(self, send):
        get_background_process(self.task, kwargs={'background_process_pk': self.process.pk})
        self.assertEqual(self.info().status, ProcessStatusEnum.RUNNING)
        self.assertEqual(self.info().progress, 25)
        send.assert_called_once()

    @patch('notify.tasks.post_save.send')
    def test_failure_preserves_progress_and_error(self, send):
        self.task.on_failure(ValueError('broken'), 'task-id', (), {}, None)
        process = self.info()
        self.assertEqual(process.status, ProcessStatusEnum.FAILED)
        self.assertEqual(process.phase, 'An error occurred: broken')
        self.assertEqual(process.progress, 25)
        self.assertEqual(process.done_steps, 1)
        self.assertIsNotNone(process.done_at)
        self.task.update_background_process(completed=True)
        self.task.update_background_process(phase='late update', step_done=True)
        self.assertEqual(self.info().status, ProcessStatusEnum.FAILED)
        self.assertEqual(self.info().phase, process.phase)
        send.assert_called_once()

    @patch('notify.tasks.post_save.send')
    def test_completion_is_terminal(self, send):
        self.task.update_background_process(completed=True)
        self.task.on_failure(ValueError('late failure'), 'task-id', (), {}, None)
        process = self.info()
        self.assertEqual(process.status, ProcessStatusEnum.COMPLETED)
        self.assertEqual(process.progress, 100)
        self.assertEqual(process.done_steps, 4)
        send.assert_called_once()

    @patch('notify.models.app.control.revoke')
    @patch('notify.models.BackgroundProcess.get_related_task_ids', return_value=[])
    @patch('notify.tasks.post_save.send')
    def test_abort_is_terminal(self, send, task_ids, revoke):
        self.process.phase = 'abort'
        self.process.save(update_fields=['phase'])
        self.task.update_background_process(completed=True)
        self.assertEqual(self.info().status, ProcessStatusEnum.ABORTED)
        self.assertEqual(self.info().progress, 25)

    @patch('notify.tasks.post_save.send')
    def test_zero_total_can_be_set(self, send):
        self.task.update_background_process(total_steps=0)
        self.assertEqual(self.info().total_steps, 0)
        self.assertEqual(self.info().progress, 0)
