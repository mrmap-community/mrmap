from unittest.mock import patch

from celery import uuid
from django.test import TestCase
from django.urls.base import reverse
from django_celery_results.models import TaskResult
from registry.models.monitoring import WMSGetCapabilitiesResult
from registry.tasks.monitoring import check_wms_get_capabilities_operation


class RunWmsMonitoringTaskTest(TestCase):

    fixtures = ['test_wms.json']

    # def setUp(self):
    #     self.task_result = TaskResult.objects.create(
    #         task_id=uuid4, task_name='registry.run_web_map_service_monitoring')

    @patch("registry.models.monitoring.WMSGetCapabilitiesResult.run_checks")
    def test_success(self, mocked_run_checks):
        task = check_wms_get_capabilities_operation.s(service_pk='cd16cc1f-3abb-4625-bb96-fbe80dbe23e3',
                                                      **{'user_pk': 'somepk'}).apply(task_id=uuid())

        print(task.result)
        wms_get_cap_result = WMSGetCapabilitiesResult.objects.all()[:1][0]

        expected_result = {
            "data": {
                "type": "WMSGetCapabilitiesResult",
                "id": f"{wms_get_cap_result.pk}",
                "links": {
                        "self": f"{reverse(viewname='registry:wmsgetcapabilitiesresult-detail', args=[wms_get_cap_result.pk])}"
                }
            }
        }
        self.assertDictEqual(d1=task.result, d2=expected_result,
                             msg="Task result does not match expection.")
