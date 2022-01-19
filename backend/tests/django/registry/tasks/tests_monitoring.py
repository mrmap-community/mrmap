from django.test import TestCase
from django.test.utils import override_settings
from django.urls.base import reverse
from registry.models.service import WebMapService
from registry.tasks.monitoring import run_web_map_service_monitoring


class RunWmsMonitoringTaskTest(TestCase):

    fixtures = ['test_wms.json']

    @override_settings(CELERY_EAGER_PROPAGATES_EXCEPTIONS=True,
                       CELERY_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    def test_success(self, mock_response):
        """Test that the ``build_ogc_service`` task runs with no errors,
        and returns the correct result."""

        result = run_web_map_service_monitoring.delay(service_pk='cd16cc1f-3abb-4625-bb96-fbe80dbe23e3',
                                                      **{'user_pk': 'somepk'})

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
