from behave import given, then, when
from django_celery_beat.models import IntervalSchedule
from registry.enums.update import UpdateJobStatusEnum
from registry.models.service import CatalogueService, WebFeatureService
from registry.models.update import (
    CatalogueServiceUpdateJob, CatalogueServiceUpdateSetting,
    WebFeatureServiceUpdateJob, WebFeatureServiceUpdateSetting,
)
from registry.tasks.update import create_csw_update_job, create_wfs_update_job


@given("the {service} periodic update has a job in state {state}")
def create_periodic_update(context, service, state):
    service_model, job_model, setting_model, create_job = {
        "WFS": (WebFeatureService, WebFeatureServiceUpdateJob,
                WebFeatureServiceUpdateSetting, create_wfs_update_job),
        "CSW": (CatalogueService, CatalogueServiceUpdateJob,
                CatalogueServiceUpdateSetting, create_csw_update_job),
    }[service]
    context.periodic_service = service_model.objects.first()
    job_model.objects.filter(service=context.periodic_service).delete()
    interval, _ = IntervalSchedule.objects.get_or_create(every=1, period="days")
    context.periodic_setting = setting_model.objects.create(
        service=context.periodic_service, interval=interval)
    context.periodic_job = job_model.objects.create(
        service=context.periodic_service, status=UpdateJobStatusEnum[state].value)
    if state == "UPDATED":
        context.periodic_job.finish(UpdateJobStatusEnum.UPDATED)
    context.create_periodic_job = create_job


@when("the periodic service update runs twice")
def run_periodic_update(context):
    context.periodic_job_ids = [context.create_periodic_job(name=context.periodic_setting.name)
                                for _ in range(2)]


@then("the periodic update reuses its unfinished job")
def check_reused_job(context):
    assert context.periodic_job_ids == [context.periodic_job.pk] * 2
    jobs = context.periodic_service.update_jobs
    assert jobs.count() == 1
    assert jobs.filter(done_at__isnull=True).count() == 1


@then("the periodic update creates one new unfinished job")
def check_new_job(context):
    first, second = context.periodic_job_ids
    assert first == second
    assert first != context.periodic_job.pk
    jobs = context.periodic_service.update_jobs
    assert jobs.count() == 2
    assert jobs.filter(done_at__isnull=True).get().pk == first
