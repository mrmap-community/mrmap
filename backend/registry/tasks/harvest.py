import os
import traceback
from os import walk
from uuid import uuid4

from celery import Task, chord, shared_task, states
from celery.signals import worker_ready
from celery.utils.log import get_task_logger
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import OperationalError, transaction
from django.utils import timezone
from extras.tasks import SingletonTask
from kombu.exceptions import OperationalError as BrokerOperationalError
from lxml import etree
from lxml.etree import Error
from MrMap.settings import FILE_IMPORT_DIR
from notify.enums import ProcessStatusEnum
from registry.enums.harvesting import (HarvestingPhaseEnum, LogLevelEnum,
                                       LogKindEnum)
from registry.exceptions.harvesting import InternalServerError
from registry.ows_lib.client.exceptions import InitialError
from requests.exceptions import RequestException

logger = get_task_logger(__name__)


class HarvestingTask(Task):
    acks_late = True
    reject_on_worker_lost = True
    autoretry_for = (RequestException, OperationalError, BrokerOperationalError, InternalServerError)
    retry_backoff = True
    retry_backoff_max = 300
    retry_kwargs = {"max_retries": 10}

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """End a harvest whose tasks gave up instead of leaving it unfinished (#690).

        A page which keeps failing never completes the chord it belongs to, so the callback of that
        chord never runs and the job keeps waiting with `done_at = null` until some worker restart
        re-publishes the whole harvest. Ending the job through the existing abort path is what the
        alert of the catalogue, the harvest history and the notification of the background process
        already answer, so nothing of that needs a second implementation here.
        """
        harvesting_job_id = (kwargs or {}).get("harvesting_job_id")
        if harvesting_job_id is None:
            # a task which is not about one job can not end one
            return

        from registry.models.harvest import HarvestingJob  # avoid circular import errors

        try:
            with transaction.atomic():
                job = HarvestingJob.objects.select_for_update().filter(
                    pk=harvesting_job_id).first()
                if job is None or job.done_at is not None:
                    # the callback which completed or aborted the job already decided about it; a
                    # late failure of a task of it must not rewrite that
                    return
                start_position = (kwargs or {}).get("start_position")
                job.log(
                    description="task gave up" + (
                        f" on page start_position={start_position}"
                        if start_position is not None else ""),
                    extented_description=(
                        f"{self.name} failed after "
                        f"{getattr(self.request, 'retries', 0)} retries\n"
                        f"{type(exc).__name__}: {exc}"),
                    level=LogLevelEnum.ERROR.value,
                    kind=LogKindEnum.REMOTE_ERROR.value,
                )
                job.phase = HarvestingPhaseEnum.ABORT.value
                job.fail_process(f"{type(exc).__name__}: {exc}")
                job.save(skip_history_when_saving=False)
        except Exception:
            # a failing harvest must not be answered with a broken worker
            logger.error(
                f"could not abort harvesting job {harvesting_job_id}: {traceback.format_exc()}")

    def after_return(self, status, retval, task_id, args, kwargs, einfo):
        """Remove the registered id of a task which reported in (#892).

        A task id is registered for the revocation of an abort, which only
        needs the work which could still be stopped: a task which ran to its
        end or gave up leaves no id behind, so the ids of a job stay bounded
        by its in-flight work instead of accumulating its whole backlog. A
        retry keeps the id - the task runs again under the same one - and a
        task which is not about one job never registered an id to begin with,
        the creation task of a job among them: its delivery id is the identity
        of the harvest for a redelivery of that message and stays registered.
        """
        if status not in (states.SUCCESS, states.FAILURE, states.REJECTED):
            return
        harvesting_job_id = (kwargs or {}).get("harvesting_job_id")
        if harvesting_job_id is None:
            return

        from registry.models.harvest import HarvestingJobTaskId  # avoid circular import errors

        try:
            HarvestingJobTaskId.objects.filter(
                job_id=harvesting_job_id, task_id=task_id).delete()
        except Exception:
            # bookkeeping must never be the reason a worker fails
            logger.error(
                f"could not remove the id {task_id} of harvesting job "
                f"{harvesting_job_id}: {traceback.format_exc()}")


class MetadataFileImportTask(HarvestingTask):
    """Base of the tasks which write stored metadata files to the database (#895).

    Building the client of the catalogue answers the request of the constructor with
    a live round trip of the stored capabilities URL, so importing a record can end
    in a read timeout or a 5xx of the remote - a failure of the infrastructure, not
    of the record. These tasks retry those errors too: what the harvest retries is
    extended by the InitialError which a 5xx or a non-xml answer of that round trip
    raises, so a catalogue hiccup redelivers the file with the existing backoff
    instead of the per-file catch of `import_md_metadata_file` ending it and silently
    losing the records it carries.
    """

    autoretry_for = HarvestingTask.autoretry_for + (InitialError,)


@worker_ready.connect
def recover_harvests_after_restart(sender, **kwargs):
    # Database state also covers a crash between commit and publishing a chord.
    sender.app.send_task("registry.tasks.harvest.recover_harvesting_jobs")


@shared_task(queue="default", base=HarvestingTask)
def recover_harvesting_jobs():
    """Resume the harvests which did not end while no worker was running.

    A worker restart leaves the messages of a running import chord in the
    broker - queued ones are untouched by it, unacked ones return through the
    visibility timeout - so a job whose tasks have not reported in has its
    backlog in the queue already. Re-chording such a job publishes the whole
    backlog a second time on top of the queued one and grows the queue per
    restart (#891); what recovery has to re-chord is a job whose run reported
    in - or which died between the commit of its phase and the publishing of
    its chord, whose own unacked message brings it back to run again.
    """
    from registry.models.harvest import HarvestingJob

    for job in HarvestingJob.objects.filter(done_at__isnull=True).iterator():
        if job.phase <= HarvestingPhaseEnum.DOWNLOAD_RECORDS and job.service_id:
            call_fetch_total_records.delay(harvesting_job_id=job.pk)
        elif job.phase == HarvestingPhaseEnum.RECORDS_TO_DB:
            if job.has_live_import_run():
                # the chord of this backlog is still in the broker and will be
                # consumed by the workers which just started (#891)
                logger.info(
                    f"harvesting job {job.pk} keeps its queued import backlog: "
                    f"recovery does not re-publish a chord which could still run")
                continue
            call_chord_md_metadata_file_to_db.delay(harvesting_job_id=job.pk)


@shared_task(queue="default", bind=True, base=HarvestingTask)
def create_harvesting_job(self, *args, **kwargs):
    from registry.models.harvest import HarvestingJob
    from registry.models.service import CatalogueService

    with transaction.atomic():
        service = CatalogueService.objects.select_for_update().get(pk=kwargs.get("service_id"))
        if not service.is_harvestable:
            return None
        # Keep the creation delivery's identity even after the harvest finishes.
        delivery_id = self.request.id or str(uuid4())
        job = HarvestingJob.objects.filter(
            celery_task_id__task_id=delivery_id).first()
        if job is None:
            # a harvest which names no step size starts from the size this catalogue is known to
            # answer - a schedule and the "harvest now" of the ui both come this way (#691)
            job, _ = HarvestingJob.objects.get_or_create(
                service=service, done_at__isnull=True,
                defaults={"max_step_size": service.max_step_size})
            job.append_celery_task_ids([delivery_id], creation=True)
        if job.done_at is None:
            transaction.on_commit(lambda: call_fetch_total_records.delay(harvesting_job_id=job.pk))
    return job.pk


@shared_task(bind=True, queue="db-routines", base=HarvestingTask, max_retries=None)
def finish_harvesting_job(self, *args, **kwargs):
    from registry.models.harvest import HarvestingJob, TemporaryMdMetadataFile
    from registry.querys.harvest_history import complete_harvest

    with transaction.atomic():
        job = HarvestingJob.objects.select_for_update().get(pk=kwargs.get("harvesting_job_id"))
        if job.done_at is not None or job.phase != HarvestingPhaseEnum.RECORDS_TO_DB:
            return
        # Recovered chords may overlap. Documented import errors are terminal.
        if TemporaryMdMetadataFile.objects.filter(job=job, has_import_error=False).exists():
            raise self.retry(countdown=5)
        complete_harvest(job.pk)


@shared_task(queue="default", base=HarvestingTask)
def call_fetch_total_records(*args, **kwargs):
    from registry.models.harvest import HarvestingJob

    try:
        with transaction.atomic():
            harvesting_job = HarvestingJob.objects.select_for_update().get(pk=kwargs.get("harvesting_job_id"))
            if harvesting_job.done_at is not None or harvesting_job.phase > HarvestingPhaseEnum.DOWNLOAD_RECORDS:
                return harvesting_job.total_records
            # Reuse the original snapshot's count when recovering downloads.
            recovering = harvesting_job.phase == HarvestingPhaseEnum.DOWNLOAD_RECORDS
            if not recovering or harvesting_job.total_records is None:
                harvesting_job.fetch_total_records()
            harvesting_job.handle_total_records_defined(recovering=recovering)
            harvesting_job.save(skip_history_when_saving=False)
            return harvesting_job.total_records
    except (RequestException, OperationalError, BrokerOperationalError, InternalServerError):
        raise
    except Exception:
        from registry.enums.harvesting import LogLevelEnum
        from registry.models.harvest import HarvestingLog

        log = HarvestingLog.objects.create(
            harvesting_job_id=kwargs.get("harvesting_job_id"),
            level=LogLevelEnum.ERROR,
            description='something went wrong during call_fetch_total_records()',
        )
        log.extented_description.save(
            name=f"harvesting_log_{log.pk}.txt",
            content=ContentFile(content=traceback.format_exc()),
        )
        raise


@shared_task(queue="download", bind=True, base=HarvestingTask)
def call_fetch_records(self, *args, **kwargs):
    from registry.models.harvest import HarvestingJob

    harvesting_job = HarvestingJob.objects.select_related("service", "service__auth").get(
        pk=kwargs.get("harvesting_job_id"))
    if harvesting_job.done_at is not None or harvesting_job.phase > HarvestingPhaseEnum.DOWNLOAD_RECORDS:
        return 0
    return harvesting_job.fetch_records(
        start_position=kwargs.get("start_position"),
        check_existing=bool(kwargs.get("recovering") or self.request.retries or
                            (self.request.delivery_info or {}).get("redelivered")),
    )


def iter_md_metadata_file_chunks(ids, batch_size=None):
    """Split the ids of stored metadata files into the batches one import task takes.

    The fan-out which writes harvested records to the database is bounded by this:
    one task per chunk instead of one task per record (#859).
    """
    size = batch_size or settings.HARVEST_IMPORT_BATCH_SIZE
    ids = list(ids)
    size = max(1, size)
    for start in range(0, len(ids), size):
        yield ids[start:start + size]


@shared_task(queue="db-routines", base=HarvestingTask)
def call_chord_md_metadata_file_to_db(*args, **kwargs):
    from registry.models.harvest import HarvestingJob, TemporaryMdMetadataFile
    from registry.querys.harvest_history import complete_harvest

    harvesting_job_id = kwargs.get("harvesting_job_id")
    with transaction.atomic():
        harvesting_job = HarvestingJob.objects.select_for_update().get(pk=harvesting_job_id)
        if harvesting_job.done_at is not None:
            return
        http_request = kwargs.get("http_request") or harvesting_job._http_request()
        ids = list(TemporaryMdMetadataFile.objects.filter(
            job_id=harvesting_job_id, has_import_error=False).values_list("pk", flat=True))
        task_ids = []
        to_db_tasks = []
        for chunk in iter_md_metadata_file_chunks(ids):
            task_id = uuid4()
            task = call_md_metadata_files_to_db.s(
                md_metadata_file_ids=chunk,
                harvesting_job_id=harvesting_job_id,
                http_request=http_request)
            task.set(task_id=str(task_id))
            task_ids.append(task_id)
            to_db_tasks.append(task)

        harvesting_job.phase = HarvestingPhaseEnum.RECORDS_TO_DB.value
        if to_db_tasks:
            callback_id = uuid4()
            callback = finish_harvesting_job.s(
                harvesting_job_id=harvesting_job_id,
                http_request=http_request,
            ).set(task_id=str(callback_id))
            harvesting_job.append_celery_task_ids(task_ids + [callback_id])
            harvesting_job.save(skip_history_when_saving=False)
            # the steps of the harvest stay granular by record, as the annotations of
            # TemporaryMdMetadataFileQuerySet.with_process_info derive them from the
            # files which are still waiting; bounding the tasks must not move the
            # progress the harvesting UI shows (#859)
            harvesting_job.report_process(
                ProcessStatusEnum.RUNNING,
                phase=str(HarvestingPhaseEnum.RECORDS_TO_DB.label),
                total_steps=len(ids) + 1)
            transaction.on_commit(lambda: chord(to_db_tasks, callback).apply_async(max_retries=300, interval=1))
        else:
            complete_harvest(harvesting_job_id)


def import_md_metadata_file(md_metadata_file_id):
    """Write a single stored metadata file to the database and return what it created.

    Answers None when there is nothing to import: the row of a successful import is deleted, so
    its absence is the proof that it was imported. The chunk task relies on this to work through
    its ids again after a retry without importing a record twice.

    Only errors of the record itself are terminal and documented on the file. Everything the
    task base of the importing tasks retries is re-raised, so the file is redelivered with the
    backoff of the harvest instead of being lost to a remote or storage outage (#895).
    """
    from registry.models.harvest import TemporaryMdMetadataFile

    try:
        with transaction.atomic():
            temporary_md_metadata_file = TemporaryMdMetadataFile.objects.select_for_update(of=("self",)).select_related(
                'job', 'job__service', 'job__service__auth',
            ).filter(pk=md_metadata_file_id).first()
            # Successful imports delete the row. Errors remain for inspection.
            if temporary_md_metadata_file is None or temporary_md_metadata_file.has_import_error:
                return
            if temporary_md_metadata_file.job.phase in [HarvestingPhaseEnum.ABORT, HarvestingPhaseEnum.ABORTED]:
                return
            results = temporary_md_metadata_file.md_metadata_file_to_db()
            return [(str(result[0].pk), result[1], result[2]) for result in results if result is not None]
    except MetadataFileImportTask.autoretry_for:
        # Infrastructure outages and remote failures are retryable, not record import
        # errors: what the task base promises to retry must reach it, or its autoretry
        # is laundered into a terminal has_import_error by the marking below (#895).
        raise
    except Exception as e:
        TemporaryMdMetadataFile.objects.filter(pk=md_metadata_file_id).update(
            has_import_error=True,
            import_error=traceback.format_exc()
        )
        logger.error(msg=e)


@shared_task(queue="db-routines", base=MetadataFileImportTask)
def call_md_metadata_file_to_db(*args, **kwargs):
    return import_md_metadata_file(kwargs.get("md_metadata_file_id"))


@shared_task(queue="db-routines", base=MetadataFileImportTask)
def call_md_metadata_files_to_db(*args, **kwargs):
    """Write a chunk of stored metadata files to the database (#859).

    One task per chunk instead of one per record bounds the broker messages, the task round-trips
    and the result writes of a harvest; the records themselves still commit one by one, so a
    record which fails is flagged and does not fail its chunk, and a retryable outage which
    raises for the whole chunk redelivers only what is not committed yet. The row of an aborted
    job is skipped per record, so an abort stops a chunk as early as it stopped a single record.
    """
    imported = []
    for md_metadata_file_id in kwargs.get("md_metadata_file_ids") or ():
        results = import_md_metadata_file(md_metadata_file_id)
        if results:
            imported.extend(results)
    return imported


@shared_task(
    queue="db-routines",
    bind=True,
    base=SingletonTask,
)
def check_for_files_to_import(self, *args, **kwargs):
    from registry.models.harvest import TemporaryMdMetadataFile

    logger.info(f"watching for new files to import in '{FILE_IMPORT_DIR}'")
    dt = timezone.now()

    db_md_metadata_file_list = []
    idx = 0
    for dirpath, subdir, files in walk(FILE_IMPORT_DIR):
        files = filter(lambda file: "ignore" not in file, files)

        if files:
            with transaction.atomic():
                for file in files:
                    filename = os.path.join(dirpath, file)
                    try:
                        xml = etree.parse(filename)
                        md_metadatas = xml.xpath(
                            "//*[local-name()='MD_Metadata']")
                        for md_metadata in md_metadatas:
                            md_xml = etree.tostring(
                                md_metadata,
                                pretty_print=True,
                                xml_declaration=True,
                                encoding="utf-8")
                            db_md_metadata_file: TemporaryMdMetadataFile = TemporaryMdMetadataFile()
                            # save the file without saving the instance in db...
                            # this will be done with bulk_create
                            db_md_metadata_file.md_metadata_file.save(
                                name=f"file_import_{dt}_{idx}",
                                content=ContentFile(
                                    content=md_xml),
                                save=False)
                            db_md_metadata_file_list.append(
                                db_md_metadata_file)
                            idx += 1

                    except Error as e:
                        new_filename = f"ignore_{dt}_{file}"
                        os.rename(filename, os.path.join(
                            dirpath, new_filename))
                        logger.error(
                            f"can't handle file cause of the following exception: {e}\n the file is renamed as {new_filename} and will be ignored.")

                if db_md_metadata_file_list:
                    db_objs = TemporaryMdMetadataFile.objects.bulk_create_with_task_scheduling(
                        objs=db_md_metadata_file_list)

                    logger.info(
                        f"start file import handling for {len(db_objs)} files")

                    return [db_obj.pk for db_obj in db_objs]

    logger.info("No files to import")
