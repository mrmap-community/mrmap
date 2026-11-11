from behave import given
from django.contrib.auth import get_user_model
from guardian.shortcuts import assign_perm
from registry.enums.update import UpdateJobStatusEnum
from registry.models.service import WebMapService
from registry.models.update import WebMapServiceUpdateJob
from registry.querys.alerts import refresh_service_alerts


@given('two map services have failed updates and User2 may view only one')
def prepare_service_alerts(context):
    """Create the state of the scenario and materialise the alert rows.

    The endpoint reads rows which its periodic refresh task writes (#1030); no
    Celery worker runs in this environment, so the step creates the state the
    task would have seen and writes its rows itself.
    """
    services = list(WebMapService.objects.order_by('pk')[:2])
    user = get_user_model().objects.get(username='User2')
    for service in services:
        WebMapServiceUpdateJob.objects.create(
            service=service, status=UpdateJobStatusEnum.ERROR.value)
    assign_perm('registry.view_webmapservice', user, services[0])
    refresh_service_alerts()
