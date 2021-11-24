from django.db import models
from django.utils.translation import gettext_lazy as _
from requests import Session, Request
from MrMap.validators import validate_get_capablities_uri
from extras.models import CommonInfo
from registry.models.security import ServiceAuthentication
from registry.xmlmapper.ogc.capabilities import get_parsed_service
from registry.models import WebMapService, WebFeatureService, CatalougeService
from django.db import transaction
from users.models import Organization
from celery import shared_task
from django.conf import settings


@shared_task(name="register_ogc_service")
def register_ogc_service(job_pk,
                         **kwargs):
    # if self.task:
    #     self.task.status = TaskStatusEnum.STARTED.value
    #     self.task.phase = "download capabilities document..."
    #     self.task.started_at = timezone.now()
    #     self.task.save()

    job = RegisterOgcServiceJob.objects.get(pk=job_pk)

    session = Session()
    session.proxies = settings.PROXIES
    request = Request(method="GET",
                      url=job.get_capabilities_url,
                      auth=job.auth)
    response = session.send(request.prepare())

    # if self.task:
    #     self.task.status = TaskStatusEnum.STARTED.value
    #     self.task.phase = "parse capabilities document..."
    #     self.task.progress = 1 / 3
    #     self.task.save()

    parsed_service = get_parsed_service(xml=response.content)

    # if self.task:
    #     self.task.phase = "persisting service..."
    #     self.task.progress = 2 / 3
    #     self.task.save()
    if parsed_service.service_type.get_field_dict().get("name").lower() == "wms":
        db_service = WebMapService.capabilities.create_from_parsed_service(parsed_service=parsed_service)
    elif parsed_service.service_type.get_field_dict().get("name").lower() == "wfs":
        db_service = WebFeatureService.capabilities.create_from_parsed_service(parsed_service=parsed_service)
    elif parsed_service.service_type.get_field_dict().get("name").lower() == "csw":
        db_service = CatalougeService.capabilities.create_from_parsed_service(parsed_service=parsed_service)
    if job.auth:
        job.auth.wms = db_service
        job.auth.save()

    # if self.task:
    #     self.task.phase = f'Done. <a href="{db_service.get_absolute_url()}">{db_service}</a>'
    #     self.task.status = TaskStatusEnum.SUCCESS.value
    #     self.task.progress = 100
    #     self.task.done_at = timezone.now()
    #     self.task.save()

    return db_service.pk


class RegisterOgcServiceJob(CommonInfo):
    get_capabilities_url = models.URLField(verbose_name=_("Service url"),
                                           help_text=_("this shall be the full get capabilities request url."),
                                           validators=[validate_get_capablities_uri],)
    collect_linked_metadata = models.BooleanField(default=True,
                                                  verbose_name=_("collect metadata"),
                                                  help_text=_("auto start collecting task after successful registering "
                                                              "which register all linked metadata records found in the "
                                                              "GetCapabilities document."))
    registering_for_organization = models.ForeignKey(to=Organization,
                                                     on_delete=models.DO_NOTHING,
                                                     verbose_name=_("Registration for organization"),
                                                     help_text=_("Select for which organization you'd like to register the service."))
    auth = models.OneToOneField(to=ServiceAuthentication,
                                on_delete=models.DO_NOTHING,
                                null=True,
                                blank=True,
                                verbose_name=_("service authentication"),
                                help_text=_("Optional credentials to authenticate against the web service."))

    def save(self, *args, **kwargs):
        self.full_clean()
        adding = False
        if self._state.adding:
            adding = True
        super().save(*args, **kwargs)
        if adding:
            transaction.on_commit(lambda: register_ogc_service.delay(job_pk=self.pk, **kwargs))
