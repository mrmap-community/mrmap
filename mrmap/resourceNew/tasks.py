from datetime import datetime

import celery.states as states
from celery import shared_task, current_task, group, chain, chord
from resourceNew.enums.service import AuthTypeEnum
from resourceNew.models import Service as DbService
from resourceNew.models import ExternalAuthentication, RemoteMetadata
from service.helper.common_connector import CommonConnector
from service.serializer.ogc.tasks import DefaultBehaviourTask, MonitoringTask
from resourceNew.parsers.capabilities import get_parsed_service
from structure.enums import PendingTaskEnum
from django_celery_results.models import TaskResult
from django.db import transaction
from django.db.models import F

PROGRESS_AFTER_DOWNLOAD_CAPABILITIES = 5
PROGRESS_AFTER_PARSING = 10
PROGRESS_AFTER_PERSISTING = 15
PROGRESS_AFTER_FETCHING_ISO_METADATA = 90


@shared_task(name="async_register_service",
             bind=True,
             base=MonitoringTask)
def register_service(self,
                     form: dict,
                     quantity: int = 1,
                     **kwargs):
    workflow = chain(create_service_from_parsed_service.s(form, quantity, **kwargs) | collect_linked_metadata.s(**kwargs))
    return workflow.apply_async()


@shared_task(name="async_get_linked_metadata",
             bind=True,
             base=DefaultBehaviourTask)
def collect_linked_metadata(self,
                            service_ids,
                            **kwargs):
    for service_id in service_ids:
        # todo: inefficient. we only need to fetch and parse the remote metadata objects one time

        remote_metadata_list = RemoteMetadata.objects.filter(service__pk=service_id)
        progress_step_size = (PROGRESS_AFTER_FETCHING_ISO_METADATA - PROGRESS_AFTER_PERSISTING)/len(remote_metadata_list)

        if self.pending_task:
            self.pending_task.phase = f"collecting linked iso metadata: 0/{len(remote_metadata_list)}"
            self.pending_task.progress = PROGRESS_AFTER_PERSISTING
            self.pending_task.save()

        header = [fetch_remote_metadata_xml.s(remote_metadata.pk, progress_step_size, **kwargs) for remote_metadata in remote_metadata_list]
        callback = parse_remote_metadata_xml_for_service.s(service_id, **kwargs)
        task = chord(header)(callback)


@shared_task(name="async_fetch_remote_metadata_xml",
             bind=True,
             base=DefaultBehaviourTask)
def fetch_remote_metadata_xml(self,
                              remote_metadata_id,
                              progress_step_size,
                              **kwargs):
    if self.pending_task and current_task:
        # todo:
        pass
        # self.pending_task.sub_tasks.add(TaskResult.objects.get(task_id=current_task.request.id))
    remote_metadata = RemoteMetadata.objects.get(pk=remote_metadata_id)
    try:
        remote_metadata.fetch_remote_content()
        if self.pending_task:
            with transaction.atomic():
                cls = self.pending_task.__class__
                pending_task = cls.objects.select_for_update().get(pk=self.pending_task.pk)
                pending_task.progress += progress_step_size
                try:
                    phase = pending_task.phase.split(":")
                    current_phase = phase[0]
                    phase_steps = phase[-1].split("/")

                    pending_task.phase = f"{current_phase}: {int(phase_steps[0])+1}/{phase_steps[-1]}"
                except Exception:
                    pass
                pending_task.save()
        return remote_metadata.id
    except Exception as e:
        i = 0
        # service_logger.exception(e, stack_info=True, exc_info=True)
        # todo: log exception in debug level
        return None


@shared_task(name="async_parse_remote_metadata_xml_for_service",
             bind=True,
             base=DefaultBehaviourTask)
def parse_remote_metadata_xml_for_service(self,
                                          remote_metadata_ids: list,
                                          service_id,
                                          **kwargs):
    if self.pending_task:
        self.pending_task.progress = PROGRESS_AFTER_FETCHING_ISO_METADATA
        self.pending_task.phase = "persisting collected iso metadata"
        self.pending_task.save()
        if current_task:
            # todo:
            pass
            # self.pending_task.sub_tasks.add(TaskResult.objects.get(task_id=current_task.request.id))
    remote_metadata_list = RemoteMetadata.objects.filter(id__in=[x for x in remote_metadata_ids if x is not None])
    progress_step_size = (100 - PROGRESS_AFTER_FETCHING_ISO_METADATA) / len(remote_metadata_list)
    successfully_list = []
    for remote_metadata in remote_metadata_list:
        try:
            db_metadata = remote_metadata.create_metadata_instance()
            successfully_list.append(db_metadata.pk)
            if self.pending_task:
                self.pending_task.progress += progress_step_size
                self.pending_task.save()
        except Exception as e:
            continue
            # service_logger.exception(e, stack_info=True, exc_info=True)
            # todo: log exception in debug level
    db_service = DbService.objects.get(pk=service_id)
    if self.pending_task:
        self.pending_task.status = PendingTaskEnum.SUCCESS.value
        self.pending_task.done_at = datetime.now()
        self.pending_task.phase = f"Done. {db_service.get_absolute_url()}"
        self.pending_task.save()
    return successfully_list


@shared_task(name="async_create_service_from_parsed_service",
             bind=True,
             base=DefaultBehaviourTask)
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
    if form["auth_type"] != AuthTypeEnum.NONE.value:
        external_auth = ExternalAuthentication(
            username=form["username"],
            password=form["password"],
            auth_type=form["auth_type"],
        )
    else:
        external_auth = None

    if self.pending_task:
        self.pending_task.status = PendingTaskEnum.STARTED.value
        self.pending_task.phase = "download capabilities document..."
        self.pending_task.save()
    connector = CommonConnector(url=form["test_url"], external_auth=external_auth)
    connector.load()

    if self.pending_task:
        self.pending_task.status = PendingTaskEnum.STARTED.value
        self.pending_task.phase = "parse capabilities document..."
        self.pending_task.progress = PROGRESS_AFTER_DOWNLOAD_CAPABILITIES
        self.pending_task.save()
        if current_task:
            # todo
            # self.pending_task.sub_tasks.add(TaskResult.objects.get(task_id=current_task.request.id))
            pass

    parsed_service = get_parsed_service(xml=connector.content)

    if self.pending_task:
        self.pending_task.phase = "persisting service..."
        self.pending_task.progress = PROGRESS_AFTER_PARSING
        self.pending_task.save()

    db_service_list = []
    for _ in range(quantity):
        db_service = DbService.xml_objects.create_from_parsed_service(parsed_service=parsed_service)

        if external_auth:
            external_auth.secured_service = db_service
            external_auth.save()
        db_service_list.append(db_service.pk)

    return db_service_list
