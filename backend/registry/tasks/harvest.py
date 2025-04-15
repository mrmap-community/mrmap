import os
import traceback
from os import walk

from celery import chord, shared_task
from celery.canvas import StampingVisitor
from celery.utils.log import get_task_logger
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from eulxml import xmlmap
from lxml.etree import Error
from MrMap.settings import FILE_IMPORT_DIR
from ows_lib.xml_mapper.iso_metadata.iso_metadata import WrappedIsoMetadata
from registry.enums.harvesting import HarvestingPhaseEnum

logger = get_task_logger(__name__)


class HarvestingJobStampingVisitor(StampingVisitor):
    def _stamp_harvesting_job_id(self, **kwargs):
        harvesting_job_id = kwargs.get("harvesting_job_id", None)
        if harvesting_job_id:
            return {'harvesting_job_id': harvesting_job_id}

    def on_signature(self, sig, **headers) -> dict:
        return self._stamp_harvesting_job_id(**headers)

    def on_callback(self, callback, **header) -> dict:
        return self._stamp_harvesting_job_id(**header)

    def on_errback(self, errback, **header) -> dict:
        return self._stamp_harvesting_job_id(**header)


@shared_task(
    queue="default",
)
def create_harvesting_job(*args, **kwargs):
    from registry.models.harvest import HarvestingJob
    return HarvestingJob.objects.create(service__pk=kwargs.get("service_id"))


@shared_task(
    bind=True,
    queue="db-routines",
)
def finish_harvesting_job(*args, **kwargs):
    from registry.models.harvest import HarvestingJob
    harvesting_job = HarvestingJob.objects.get(
        pk=kwargs.get("harvesting_job_id"))
    harvesting_job.phase = HarvestingPhaseEnum.COMPLETED.value
    harvesting_job.save(skip_history_when_saving=False)


@shared_task(
    queue="default",
)
def call_fetch_total_records(*args, **kwargs):
    from registry.models.harvest import HarvestingJob
    harvesting_job: HarvestingJob = HarvestingJob.objects.select_related("service").get(
        pk=kwargs.get("harvesting_job_id"))
    total_records = harvesting_job.fetch_total_records()

    harvesting_job.handle_total_records_defined()

    return total_records


@shared_task(
    queue="download",
)
def call_fetch_records(*args, **kwargs):
    from registry.models.harvest import HarvestingJob

    harvesting_job: HarvestingJob = HarvestingJob.objects.select_related("service").get(
        pk=kwargs.get("harvesting_job_id"))

    fetched_records = harvesting_job.fetch_records(
        start_position=kwargs.get("start_position"))

    return fetched_records


@shared_task(
    queue="db-routines",
)
def call_chord_md_metadata_file_to_db(*args, **kwargs):
    from registry.models.harvest import HarvestingJob, TemporaryMdMetadataFile

    harvesting_job_id = kwargs.get("harvesting_job_id")
    http_request = kwargs.get("http_request")

    ids = TemporaryMdMetadataFile.objects.filter(
        job_id=harvesting_job_id).values_list("pk", flat=True)

    to_db_tasks = [
        call_md_metadata_file_to_db.s(
            md_metadata_file_id=id,
            harvesting_job_id=harvesting_job_id,
            http_request=http_request)
        for id in ids
    ]
    harvesting_job = HarvestingJob.objects.get(pk=harvesting_job_id)
    if to_db_tasks:
        c = chord(to_db_tasks)
        c.link(finish_harvesting_job.s(
            harvesting_job_id=harvesting_job_id,
            http_request=http_request,
        ))
        c.stamp(visitor=HarvestingJobStampingVisitor())
        c()
        harvesting_job.phase = HarvestingPhaseEnum.RECORDS_TO_DB.value
    else:
        harvesting_job.phase = HarvestingPhaseEnum.COMPLETED.value
    harvesting_job.save(skip_history_when_saving=False)


@shared_task(
    queue="db-routines",
)
def call_md_metadata_file_to_db(*args, **kwargs):
    md_metadata_file_id = kwargs.get("md_metadata_file_id")
    try:
        from registry.models.harvest import TemporaryMdMetadataFile

        temporary_md_metadata_file: TemporaryMdMetadataFile = TemporaryMdMetadataFile.objects.select_related(
            'job',
            'job__service',
            'job__service__auth',
        ).get(pk=md_metadata_file_id)

        db_metadata, update, exists = temporary_md_metadata_file.md_metadata_file_to_db()

        return str(db_metadata.pk), update, exists
    except Exception:
        TemporaryMdMetadataFile.objects.select_for_update().filter(pk=md_metadata_file_id).update(
            has_import_error=True,
            import_error=traceback.format_exc()
        )


@shared_task(
    queue="db-routines",
)
def check_for_files_to_import(*args, **kwargs):
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
                        metadata_xml: WrappedIsoMetadata = xmlmap.load_xmlobject_from_file(
                            filename=filename,
                            xmlclass=WrappedIsoMetadata)

                        for iso_metadata in metadata_xml.iso_metadata:
                            db_md_metadata_file: TemporaryMdMetadataFile = TemporaryMdMetadataFile()
                            # save the file without saving the instance in db...
                            # this will be done with bulk_create
                            db_md_metadata_file.md_metadata_file.save(
                                name=f"file_import_{dt}_{idx}",
                                content=ContentFile(
                                    content=iso_metadata.serialize()),
                                save=False)
                            db_md_metadata_file_list.append(
                                db_md_metadata_file)
                            os.remove(filename)
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

    logger.info(f"No files to import")
