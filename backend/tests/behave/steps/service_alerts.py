from behave import given
from django.contrib.auth import get_user_model
from guardian.shortcuts import assign_perm
from registry.enums.update import UpdateJobStatusEnum
from registry.models.service import WebMapService
from registry.models.update import WebMapServiceUpdateJob


@given('two map services have failed updates and User2 may view only one')
def prepare_service_alerts(context):
    services = list(WebMapService.objects.order_by('pk')[:2])
    user = get_user_model().objects.get(username='User2')
    for service in services:
        WebMapServiceUpdateJob.objects.create(
            service=service, status=UpdateJobStatusEnum.ERROR.value)
    assign_perm('registry.view_webmapservice', user, services[0])
