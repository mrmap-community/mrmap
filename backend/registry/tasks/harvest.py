import os
import traceback
from os import walk
from uuid import uuid4

from celery import Task, chord, shared_task
from celery.signals import worker_ready
from celery.utils.log import get_task_logger
from django.core.files.base import ContentFile
from django.db import OperationalError, transaction
from django.utils import timezone
from extras.tasks import SingletonTask
from kombu.exceptions import OperationalError as BrokerOperationalError
from lxml import etree
from lxml.etree import Error
from MrMap.settings import FILE_IMPORT_DIR
from registry.enums.harvesting import HarvestingPhaseEnum
from registry.exceptions.harvesting import InternalServerError
from requests.exceptions import RequestException

logger = get_task_logger(__name__)


class HarvestingTask(Task):
    acks_late = True
    reject_on_worker_lost = True
    autoretry_for = (RequestException, OperationalError, BrokerOperationalError, InternalServerError)
    retry_backoff = True
    retry_backoff_max = 300
    retry_kwargs = {"max_retries": 10}


@worker_ready.connect
def recover_harvests_after_restart(sender, **kwargs):
    # Database state also covers a crash between commit and publishing a chord.
    sender.app.send_task("registry.tasks.harvest.recover_harvesting_jobs")


@shared_task(queue="default", base=HarvestingTask)
def recover_harvesting_jobs():
    from registry.models.harvest import HarvestingJob

    for job in HarvestingJob.objects.filter(done_at__isnull=True).iterator():
        if job.phase <= HarvestingPhaseEnum.DOWNLOAD_RECORDS and job.service_id:
            call_fetch_total_records.delay(harvesting_job_id=job.pk)
        elif job.phase == HarvestingPhaseEnum.RECORDS_TO_DB:
            call_chord_md_metadata_file_to_db.delay(harvesting_job_id=job.pk)


@shared_task(queue="default", bind=True, base=HarvestingTask)
def create_harvesting_job(self, *args, **kwargs):
    from registry.models.harvest import HarvestingJob
    from registry.models.service import CatalogueService

    with transaction.atomic():
        service = CatalogueService.objects.select_for_update().get(pk=kwargs.get("service_id"))
        # Keep the creation delivery's identity even after the harvest finishes.
        delivery_id = self.request.id or str(uuid4())
        job = HarvestingJob.objects.filter(celery_task_ids__contains=[delivery_id]).first()
        if job is None:
            job, _ = HarvestingJob.objects.get_or_create(service=service, done_at__isnull=True)
            job.append_celery_task_ids([delivery_id])
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
        ids = TemporaryMdMetadataFile.objects.filter(
            job_id=harvesting_job_id, has_import_error=False).values_list("pk", flat=True)
        task_ids = []
        to_db_tasks = []
        for _id in ids:
            task_id = uuid4()
            task = call_md_metadata_file_to_db.s(
                md_metadata_file_id=_id,
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
            transaction.on_commit(lambda: chord(to_db_tasks, callback).apply_async(max_retries=300, interval=1))
        else:
            complete_harvest(harvesting_job_id)


@shared_task(queue="db-routines", base=HarvestingTask)
def call_md_metadata_file_to_db(*args, **kwargs):
    from registry.models.harvest import TemporaryMdMetadataFile

    md_metadata_file_id = kwargs.get("md_metadata_file_id")
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
    except OperationalError:
        # Infrastructure outages are retryable, not record import errors.
        raise
    except Exception as e:
        TemporaryMdMetadataFile.objects.filter(pk=md_metadata_file_id).update(
            has_import_error=True,
            import_error=traceback.format_exc()
        )
        logger.error(msg=e)


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
