from django.utils import timezone
from celery import shared_task, chain, chord, group
from requests import Session, Request
from requests.auth import HTTPDigestAuth

from MrMap.settings import PROXIES
from registry.enums.service import AuthTypeEnum
from registry.models import Service as DbService, FeatureType, DatasetMetadata
from registry.models import RemoteMetadata
from registry.models.security import ExternalAuthentication
from jobs.tasks import NewJob, CurrentTask
from registry.xmlmapper.ogc.capabilities import get_parsed_service
from jobs.enums import TaskStatusEnum
from django.db import transaction
from django.urls import reverse
from django.conf import settings


@shared_task(name="async_register_service",
             bind=True,
             base=NewJob)
def register_service(self,
                     form: dict,
                     quantity: int = 1,
                     **kwargs):
    # todo: create task objects here and pass them to the three tasks
    workflow = chain(create_service_from_parsed_service.s(form, quantity, **kwargs) |
                     group(schedule_collect_feature_type_elements.s(**kwargs) | schedule_collect_linked_metadata.s(**kwargs)))
    workflow.apply_async()
    return self.job.pk


@shared_task(name="async_collect_feature_type_elements",
             bind=True,
             base=CurrentTask, )
def schedule_collect_feature_type_elements(self,
                                           service_id,
                                           **kwargs):
    feature_type_list = FeatureType.objects.filter(service__pk=service_id)
    if feature_type_list:
        if self.task:
            self.task.phase = f"collecting feature type elements: 0/{len(feature_type_list)}"
            self.task.save()
        progress_step_size = 100 / len(feature_type_list)

        header = [create_feature_type_elements.s(feature_type.pk, progress_step_size, **kwargs)
                  for feature_type in feature_type_list]
        callback = set_task_success.s(**kwargs)
        chord(header)(callback)
    else:
        if self.task:
            self.task.delete()
    return service_id


@shared_task(name="create_feature_type_elements",
             bind=True,
             base=CurrentTask,
             queue="download_described_elements")
def create_feature_type_elements(self,
                                 feature_type_id,
                                 progress_step_size,
                                 **kwargs):
    feature_type = FeatureType.objects.get(pk=feature_type_id)
    feature_type.fetch_describe_feature_type_document()
    elements = feature_type.create_element_instances()
    if self.task:
        # CAREFULLY!!!: this is a race condition in parallel execution, cause all tasks will waiting for the task
        # which looks the pending task for updating progress and phase.
        with transaction.atomic():
            cls = self.task.__class__
            task = cls.objects.select_for_update().get(pk=self.task.pk)
            if not task.started_at:
                task.started_at = timezone.now()
            task.status = TaskStatusEnum.STARTED.value
            task.progress += progress_step_size
            try:
                phase = task.phase.split(":")
                current_phase = phase[0]
                phase_steps = phase[-1].split("/")

                task.phase = f"{current_phase}: {int(phase_steps[0]) + 1}/{phase_steps[-1]}"
            except Exception:
                pass
            task.save()
    return [element.pk for element in elements]


@shared_task(name="set_task_success",
             bind=True,
             base=CurrentTask)
def set_task_success(self,
                     *args,
                     **kwargs):
    if self.task:
        self.task.progress = 100
        self.task.status = TaskStatusEnum.SUCCESS.value
        self.task.done_at = timezone.now()
        self.task.save()


@shared_task(name="async_collect_linked_metadata",
             bind=True,
             base=CurrentTask)
def schedule_collect_linked_metadata(self,
                                     service_id,
                                     **kwargs):
    remote_metadata_list = RemoteMetadata.objects.filter(service__pk=service_id)
    if remote_metadata_list:
        progress_step_size = 100 / len(remote_metadata_list) / 2
        if self.task:
            self.task.phase = f"collecting linked iso metadata: 0/{len(remote_metadata_list)}"
            self.task.save()

        header = [fetch_remote_metadata_xml.s(remote_metadata.pk, progress_step_size, **kwargs) for remote_metadata in remote_metadata_list]
        callback = parse_remote_metadata_xml_for_service.s(progress_step_size, **kwargs)
        chord(header)(callback)
    return service_id


@shared_task(name="async_fetch_remote_metadata_xml",
             bind=True,
             base=CurrentTask,
             queue="download_iso_metadata")
def fetch_remote_metadata_xml(self,
                              remote_metadata_id,
                              progress_step_size,
                              **kwargs):
    remote_metadata = RemoteMetadata.objects.get(pk=remote_metadata_id)
    try:
        remote_metadata.fetch_remote_content()
        if self.task:
            # CAREFULLY!!!: this is a race condition in parallel execution, cause all tasks will waiting for the task
            # which looks the pending task for updating progress and phase.
            with transaction.atomic():
                cls = self.task.__class__
                task = cls.objects.select_for_update().get(pk=self.task.pk)
                task.status = TaskStatusEnum.STARTED.value
                if not task.started_at:
                    task.started_at = timezone.now()
                task.progress += progress_step_size
                try:
                    phase = task.phase.split(":")
                    current_phase = phase[0]
                    phase_steps = phase[-1].split("/")

                    task.phase = f"{current_phase}: {int(phase_steps[0])+1}/{phase_steps[-1]}"
                except Exception:
                    pass
                task.save()
        return remote_metadata.id
    except Exception:
        # settings.ROOT_LOGGER.exception(e, stack_info=True, exc_info=True)
        # TODO: log exception in debug level
        return None


@shared_task(name="async_parse_remote_metadata_xml_for_service",
             bind=True,
             base=CurrentTask)
def parse_remote_metadata_xml_for_service(self,
                                          remote_metadata_ids: list,
                                          progress_step_size,
                                          **kwargs):
    if self.task:
        self.task.phase = "persisting collected iso metadata"
        self.task.save()
    remote_metadata_list = RemoteMetadata.objects.filter(id__in=[x for x in remote_metadata_ids if x is not None])
    successfully_list = []
    dataset_list = []
    if remote_metadata_list:
        for remote_metadata in remote_metadata_list:
            try:
                db_metadata = remote_metadata.create_metadata_instance()
                successfully_list.append(db_metadata.pk)
                if isinstance(db_metadata, DatasetMetadata):
                    dataset_list.append(db_metadata.pk)
            except Exception as e:
                settings.ROOT_LOGGER.exception(e, stack_info=True, exc_info=True)
            if self.task:
                self.task.refresh_from_db()
                self.task.progress += progress_step_size
                self.task.save()
    if self.task:
        self.task.status = TaskStatusEnum.SUCCESS.value
        self.task.done_at = timezone.now()
        self.task.phase = f'Done. <a href="{reverse("registry:dataset_metadata_list")}?id__in={",".join(str(pk) for pk in dataset_list)}">dataset metadata</a>'
        self.task.save()
    return successfully_list


@shared_task(name="async_create_service_from_parsed_service",
             bind=True,
             base=CurrentTask)
def create_service_from_parsed_service(self,
                                       form: dict,
                                       quantity: int = 1,
                                       **kwargs):
    """ Async call of new service creation

    Since redis is used as broker, the objects can not be passed directly into the function. They have to be resolved using
    their ids, since the objects are not easily serializable using json

    Args:
        form (dict): the cleaned_data dict of the used RegisterServiceForm
        quantity (int): how many services from this url are registered in one process. Default is 1. Only used for
                        developing purposes.
    Returns:
        db_service_list (list): the id's of the created service object(s)
    """
    if self.task:
        self.task.status = TaskStatusEnum.STARTED.value
        self.task.phase = "download capabilities document..."
        self.task.started_at = timezone.now()
        self.task.save()

    auth = form.get("auth_type", None)
    external_auth = None
    if auth:
        external_auth = ExternalAuthentication(username=form["username"],
                                               password=form["password"],
                                               auth_type=form["auth_type"],
                                               test_url=form["test_url"])
        if self.service.external_authentication.auth_type == AuthTypeEnum.BASIC.value:
            auth = (form["username"], form["password"])
        elif self.service.external_authentication.auth_type == AuthTypeEnum.DIGEST.value:
            auth = HTTPDigestAuth(username=form["username"],
                                  password=form["password"])
    session = Session()
    session.proxies = PROXIES
    request = Request(method="GET",
                      url=form["test_url"],
                      auth=auth)
    response = session.send(request.prepare())

    if self.task:
        self.task.status = TaskStatusEnum.STARTED.value
        self.task.phase = "parse capabilities document..."
        self.task.progress = 1 / 3
        self.task.save()

    parsed_service = get_parsed_service(xml=response.content)

    if self.task:
        self.task.phase = "persisting service..."
        self.task.progress = 2 / 3
        self.task.save()

    db_service = DbService.capabilities.create_from_parsed_service(parsed_service=parsed_service)
    if external_auth:
        external_auth.secured_service = db_service
        external_auth.save()

    if self.task:
        self.task.phase = f'Done. <a href="{db_service.get_absolute_url()}">{db_service}</a>'
        self.task.status = TaskStatusEnum.SUCCESS.value
        self.task.progress = 100
        self.task.done_at = timezone.now()
        self.task.save()

    return db_service.pk
