from django.test import TestCase
from django.test.utils import override_settings
from tests.django.registry.tasks.tests_service import build_ogc_service


class BuildOgcServiceTaskTest(TestCase):

    @override_settings(CELERY_EAGER_PROPAGATES_EXCEPTIONS=True,
                       CELERY_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    def test_success(self):
        """Test that the ``add`` task runs with no errors,
        and returns the correct result."""
        # result = add.delay(8, 8)

        # self.assertEquals(result.get(), 16)
        # self.assertTrue(result.successful())
        result = build_ogc_service(get_capabilities_url='http://someurl',
                                   collect_metadata_records=False,
                                   auth=None,
                                   **{'user_pk': 'somepk'}).delay()
        self.assertTrue(result)
