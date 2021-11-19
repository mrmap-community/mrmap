import django_rq
from django.db import models
from django.utils.translation import gettext_lazy as _
from requests.auth import HTTPDigestAuth
from requests import Session, Request
from MrMap.validators import validate_get_capablities_uri
from jobs.models import Job, Task
from registry.models.security import ServiceAuthentication
from registry.xmlmapper.ogc.capabilities import get_parsed_service
from registry.enums.service import AuthTypeEnum
from jobs.enums import TaskStatusEnum
from django.utils import timezone
from django.conf import settings
from registry.models import WebMapService
from django.db import transaction
from users.models import Organization


class RegisterWebMapService(Job):
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
    username = models.CharField(max_length=255,
                                null=True,
                                blank=True,
                                verbose_name=_("username"),
                                help_text=_("the username used for the authentication."))
    password = models.CharField(max_length=500,
                                null=True,
                                blank=True,
                                verbose_name=_("password"),
                                help_text=_("the password used for the authentication."))
    auth_type = models.CharField(max_length=12,
                                 choices=AuthTypeEnum.as_choices(),
                                 null=True,
                                 blank=True,
                                 verbose_name=_("authentication type"),
                                 help_text=_("kind of authentication mechanism shall used."))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "Register Service"

    def save(self, *args, **kwargs):
        adding = False
        if self._state.adding:
            adding = True
        super().save(*args, **kwargs)
        task = BuildWebMapServiceTask.objects.create(job=self)

        if adding:
            queue = django_rq.get_queue('default')
            transaction.on_commit(lambda: queue.enqueue(task.create_service_from_parsed_service, task_pk=task.pk))


class BuildWebMapServiceTask(Task):
    job = models.OneToOneField(to=RegisterWebMapService,
                               on_delete=models.CASCADE,
                               related_name="build_service_task",
                               related_query_name="build_service_task",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "Register Service"

    @classmethod
    def create_service_from_parsed_service(cls, task_pk):
        task = BuildWebMapServiceTask.objects.get(pk=task_pk)
        task.status = TaskStatusEnum.STARTED.value
        task.phase = "download capabilities document..."
        task.started_at = timezone.now()
        task.save()

        auth = None
        service_auth = None
        if task.register_service_job.auth_type:
            service_auth = ServiceAuthentication(username=task.register_service_job.username,
                                                 password=task.register_service_job.password,
                                                 auth_type=task.register_service_job.auth_type,
                                                 test_url=task.register_service_job.test_url)
            if task.register_service_job.auth_type == AuthTypeEnum.BASIC.value:
                auth = (task.register_service_job.username, task.register_service_job.password)
            elif task.register_service_job.auth_type == AuthTypeEnum.DIGEST.value:
                auth = HTTPDigestAuth(username=task.register_service_job.username,
                                      password=task.register_service_job.password)
        session = Session()
        session.proxies = settings.PROXIES
        request = Request(method="GET",
                          url=task.register_service_job.test_url,
                          auth=auth)
        response = session.send(request.prepare())

        task.status = TaskStatusEnum.STARTED.value
        task.phase = "parse capabilities document..."
        task.progress = 1 / 3
        task.save()

        parsed_service = get_parsed_service(xml=response.content)

        task.phase = "persisting service..."
        task.progress = 2 / 3
        task.save()

        db_service = WebMapService.capabilities.create_from_parsed_service(parsed_service=parsed_service)
        if service_auth:
            service_auth.secured_service = db_service
            service_auth.save()

        task.phase = f'Done. <a href="{db_service.get_absolute_url()}">{db_service}</a>'
        task.status = TaskStatusEnum.SUCCESS.value
        task.progress = 100
        task.done_at = timezone.now()
        task.save()

        return db_service.pk
