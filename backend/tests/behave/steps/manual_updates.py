from behave import given, then
from django.contrib.auth import get_user_model
from django_celery_beat.models import IntervalSchedule
from guardian.shortcuts import assign_perm
from registry.enums.update import UpdateJobStatusEnum
from registry.models import WebMapService, WebMapServiceUpdateJob, WebMapServiceUpdateSetting


SERVICE_ID = "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"


@given("User1 can manually update the WMS")
def authorize_manual_update(context):
    user = get_user_model().objects.get(username="User1")
    assign_perm("registry.add_webmapserviceupdatejob", user)
    assign_perm("registry.change_webmapservice", user, WebMapService.objects.get(pk=SERVICE_ID))


@given("the WMS has no automatic update settings")
def remove_update_settings(context):
    WebMapServiceUpdateSetting.objects.filter(service_id=SERVICE_ID).delete()
    context.update_settings = []


@given("the WMS has a disabled automatic update setting")
def disable_update_setting(context):
    WebMapServiceUpdateSetting.objects.filter(service_id=SERVICE_ID).delete()
    interval, _ = IntervalSchedule.objects.get_or_create(every=1, period="days")
    WebMapServiceUpdateSetting.objects.create(service_id=SERVICE_ID, interval=interval, enabled=False)
    context.update_settings = list(WebMapServiceUpdateSetting.objects.filter(service_id=SERVICE_ID).values())


@given("the WMS has an update awaiting review")
def create_review_job(context):
    WebMapServiceUpdateJob.objects.create(service_id=SERVICE_ID, status=UpdateJobStatusEnum.REVIEW_REQUIRED.value)


@then("the WMS automatic update settings are unchanged")
def unchanged_update_settings(context):
    assert list(WebMapServiceUpdateSetting.objects.filter(service_id=SERVICE_ID).values()) == context.update_settings
