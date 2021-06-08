from django.utils import timezone
from celery import shared_task, chain, chord, group
from resourceNew.enums.service import AuthTypeEnum, OGCServiceEnum
from resourceNew.models import Service as DbService, FeatureType
from resourceNew.models import ExternalAuthentication, RemoteMetadata
from service.helper.common_connector import CommonConnector
from main.tasks import DefaultBehaviourTask, MonitoringTask
from resourceNew.parsers.ogc.capabilities import get_parsed_service
from service.settings import service_logger
from structure.enums import PendingTaskEnum
from django.db import transaction
from django.conf import settings


# todo: not thread save
PROGRESS_AFTER_DOWNLOAD_CAPABILITIES = 5
PROGRESS_AFTER_CAPABILITIES_PARSING = 10
PROGRESS_AFTER_SERVICE_PERSISTING = 15
PROGRESS_AFTER_FETCHING_ISO_METADATA = 80
PROGRESS_AFTER_ISO_METADATA_PERSISTING = 100
PROGRESS_AFTER_FEATURE_TYPE_ELEMENTS_PERSISTING = 100


@shared_task(name="async_register_service",
             bind=True,
             base=MonitoringTask)
def register_service(self,
                     form: dict,
                     quantity: int = 1,
                     **kwargs):
    workflow = chain(create_service_from_parsed_service.s(form, quantity, **kwargs) |
                        group(schedule_collect_feature_type_elements.s(**kwargs) |
                              schedule_collect_linked_metadata.s(**kwargs))
                     )
    workflow.apply_async(countdown=settings.CELERY_DEFAULT_COUNTDOWN)
    return self.pending_task.pk


@shared_task(name="async_collect_feature_type_elements",
             bind=True,
             base=DefaultBehaviourTask,)
def schedule_collect_feature_type_elements(self,
                                           service_id,
                                           **kwargs):
    feature_type_list = FeatureType.objects.filter(service__pk=service_id)
    if feature_type_list:
        progress_step_size = (PROGRESS_AFTER_FEATURE_TYPE_ELEMENTS_PERSISTING -
                              PROGRESS_AFTER_ISO_METADATA_PERSISTING) / len(feature_type_list)
        group(create_feature_type_elements.s(feature_type.pk, progress_step_size, **kwargs)
              for feature_type in feature_type_list)()
    return service_id


@shared_task(name="create_feature_type_elements",
             bind=True,
             base=DefaultBehaviourTask,
             queue="download_described_elements")
def create_feature_type_elements(self,
                                 feature_type_id,
                                 progress_step_size,
                                 **kwargs):
    feature_type = FeatureType.objects.get(pk=feature_type_id)
    feature_type.fetch_describe_feature_type_document()
    elements = feature_type.create_element_instances()
    if self.pending_task:
        # CAREFULLY!!!: this is a race condition in parallel execution, cause all tasks will waiting for the task
        # which looks the pending task for updating progress and phase.
        with transaction.atomic():
            cls = self.pending_task.__class__
            pending_task = cls.objects.select_for_update().get(pk=self.pending_task.pk)
            pending_task.progress += progress_step_size
            try:
                phase = pending_task.phase.split(":")
                current_phase = phase[0]
                phase_steps = phase[-1].split("/")

                pending_task.phase = f"{current_phase}: {int(phase_steps[0]) + 1}/{phase_steps[-1]}"
            except Exception:
                pass
            pending_task.save()
    return [element.pk for element in elements]


@shared_task(name="async_collect_linked_metadata",
             bind=True,
             base=DefaultBehaviourTask)
def schedule_collect_linked_metadata(self,
                                     service_id,
                                     **kwargs):
    remote_metadata_list = RemoteMetadata.objects.filter(service__pk=service_id)
    if remote_metadata_list:
        progress_step_size = (PROGRESS_AFTER_FETCHING_ISO_METADATA - PROGRESS_AFTER_SERVICE_PERSISTING) / len(remote_metadata_list)
        if self.pending_task:
            self.pending_task.phase = f"collecting linked iso metadata: 0/{len(remote_metadata_list)}"
            self.pending_task.progress = PROGRESS_AFTER_SERVICE_PERSISTING
            self.pending_task.save()

        header = [fetch_remote_metadata_xml.s(remote_metadata.pk, progress_step_size, **kwargs) for remote_metadata in remote_metadata_list]
        callback = parse_remote_metadata_xml_for_service.s(service_id, **kwargs)
        chord(header)(callback)
    return service_id


@shared_task(name="async_fetch_remote_metadata_xml",
             bind=True,
             base=DefaultBehaviourTask,
             queue="download_iso_metadata")
def fetch_remote_metadata_xml(self,
                              remote_metadata_id,
                              progress_step_size,
                              **kwargs):
    remote_metadata = RemoteMetadata.objects.get(pk=remote_metadata_id)
    try:
        remote_metadata.fetch_remote_content()
        if self.pending_task:
            # CAREFULLY!!!: this is a race condition in parallel execution, cause all tasks will waiting for the task
            # which looks the pending task for updating progress and phase.
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
    remote_metadata_list = RemoteMetadata.objects.filter(id__in=[x for x in remote_metadata_ids if x is not None])
    successfully_list = []
    if remote_metadata_list:
        progress_step_size = (100 - PROGRESS_AFTER_FETCHING_ISO_METADATA) / len(remote_metadata_list)
        for remote_metadata in remote_metadata_list:
            try:
                db_metadata = remote_metadata.create_metadata_instance()
                successfully_list.append(db_metadata.pk)
            except Exception as e:
                service_logger.exception(e, stack_info=True, exc_info=True)
            if self.pending_task:
                self.pending_task.refresh_from_db()
                self.pending_task.progress += progress_step_size
                self.pending_task.save()
    db_service = DbService.objects.get(pk=service_id)
    if self.pending_task:
        self.pending_task.status = PendingTaskEnum.SUCCESS.value
        self.pending_task.done_at = timezone.now()
        self.pending_task.progress = 100
        self.pending_task.phase = f'Done. <a href="{db_service.get_absolute_url()}">{db_service}</a>'
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
        self.pending_task.started_at = timezone.now()
        self.pending_task.save()
    connector = CommonConnector(url=form["test_url"], external_auth=external_auth)
    connector.load()

    if self.pending_task:
        self.pending_task.status = PendingTaskEnum.STARTED.value
        self.pending_task.phase = "parse capabilities document..."
        self.pending_task.progress = PROGRESS_AFTER_DOWNLOAD_CAPABILITIES
        self.pending_task.save()

    parsed_service = get_parsed_service(xml=connector.content)

    if self.pending_task:
        self.pending_task.phase = "persisting service..."
        self.pending_task.progress = PROGRESS_AFTER_CAPABILITIES_PARSING
        self.pending_task.save()

    db_service = DbService.xml_objects.create_from_parsed_service(parsed_service=parsed_service)
    if external_auth:
        external_auth.secured_service = db_service
        external_auth.save()

    if self.pending_task:
        no_iso_metadata = False
        no_feature_types = False
        try:
            db_service.remote_metadata
        except:
            no_iso_metadata = True
        try:
            db_service.featuretype
        except:
            no_feature_types = True

        if no_iso_metadata and no_feature_types:
            # we are done... all subprocesses will skipped
            self.pending_task.phase = f'Done. <a href="{db_service.get_absolute_url()}">{db_service}</a>'
            self.pending_task.progress = 100
            self.pending_task.save()

    global PROGRESS_AFTER_FETCHING_ISO_METADATA, PROGRESS_AFTER_ISO_METADATA_PERSISTING
    if db_service.service_type_name == OGCServiceEnum.WFS.value:
        PROGRESS_AFTER_FETCHING_ISO_METADATA = 60
        PROGRESS_AFTER_ISO_METADATA_PERSISTING = 80
    elif db_service.service_type_name == OGCServiceEnum.WMS.value:
        PROGRESS_AFTER_FETCHING_ISO_METADATA = 80
        PROGRESS_AFTER_ISO_METADATA_PERSISTING = 100

    return db_service.pk
