import json
from unittest.mock import patch
from uuid import uuid4

from celery.app.task import Task
from django.test import TestCase
from django.test.utils import override_settings
from django.urls.base import reverse
from django_celery_results.models import TaskResult
from registry.models.service import WebMapService
from registry.tasks.monitoring import run_web_map_service_monitoring


class RunWmsMonitoringTaskTest(TestCase):

    fixtures = ['test_wms.json']

    def setUp(self):
        self.task_result = TaskResult.objects.create(
            task_id=uuid4, task_name='registry.run_web_map_service_monitoring')

    @override_settings(CELERY_EAGER_PROPAGATES_EXCEPTIONS=True,
                       CELERY_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(Task, 'request')
    def test_success(self, mocked_task):
        mocked_task.return_value.id = self.task_result.task_id
        print("calling task")
        task = run_web_map_service_monitoring.delay(service_pk='cd16cc1f-3abb-4625-bb96-fbe80dbe23e3',
                                                    **{'user_pk': 'somepk'})
        print(task)
        result = task.get()
        print(result)

        # expected_result = {
        #     "data": {
        #         "type": "WebMapService",
        #         "id": f"{db_service.pk}",
        #         "links": {
        #             "self": f"{reverse(viewname='registry:wms-detail', args=[db_service.pk])}"
        #         }
        #     }
        # }
        # self.assertDictEqual(d1=result.result, d2=expected_result,
        #                      msg="Task result does not match expection.")
