
import os
from logging import Logger
from os import walk

from celery import shared_task
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from eulxml import xmlmap
from lxml.etree import Error
from MrMap.settings import FILE_IMPORT_DIR
from ows_lib.xml_mapper.iso_metadata.iso_metadata import WrappedIsoMetadata
from registry.models.harvest import HarvestingJob, TemporaryMdMetadataFile
from requests.exceptions import Timeout

logger: Logger = settings.ROOT_LOGGER


@shared_task(
    queue="default",
    priority=2
)
def create_harvesting_job(service_id):
    return HarvestingJob.objects.create(service__pk=service_id)


@shared_task(
    queue="default",
    autoretry_for=(Timeout,),
    retry_kwargs={'max_retries': 5},
    priority=10,
)
def call_fetch_total_records(harvesting_job_id):
    harvesting_job: HarvestingJob = HarvestingJob.objects.select_related("service").get(
        pk=harvesting_job_id)
    return harvesting_job.fetch_total_records()


@shared_task(
    queue="download",
    autoretry_for=(Timeout,),
    retry_kwargs={'max_retries': 5},
    priority=3
)
def call_fetch_records(harvesting_job_id,
                       start_position,
                       **kwargs):
    harvesting_job: HarvestingJob = HarvestingJob.objects.select_related("service").get(
        pk=harvesting_job_id)
    return harvesting_job.fetch_records(start_position=start_position)


@shared_task(
    queue="db-routines",
    retry_kwargs={'max_retries': 5},
    priority=6
)
def call_md_metadata_file_to_db(md_metadata_file_id: int):
    temporary_md_metadata_file: TemporaryMdMetadataFile = TemporaryMdMetadataFile.objects.get(
        pk=md_metadata_file_id)
    dataset_metadata = temporary_md_metadata_file.md_metadata_file_to_db()
    return dataset_metadata.pk


@shared_task(
    queue="db-routines",
    priority=8
)
def check_for_files_to_import():
    logger.info(f"watching for new files to import in '{FILE_IMPORT_DIR}'")
    dt = timezone.now()

    db_md_metadata_file_list = []
    idx = 0
    for dirpath, subdir, files in walk(FILE_IMPORT_DIR):
        for file in files:
            if "ignore" in file:
                continue
            filename = os.path.join(dirpath, file)
            try:
                with transaction.atomic():
                    metadata_xml: WrappedIsoMetadata = xmlmap.load_xmlobject_from_file(filename=filename,
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
                        db_md_metadata_file_list.append(db_md_metadata_file)
                        os.remove(filename)
                        idx += 1
            except Error as e:
                new_filename = f"ignore_{dt}_{file}"
                os.rename(filename, os.path.join(dirpath, new_filename))
                logger.error(
                    f"can't handle file cause of the following exception: {e}\n the file is renamed as {new_filename} and will be ignored.")

    db_objs = TemporaryMdMetadataFile.objects.bulk_create_with_task_scheduling(
        objs=db_md_metadata_file_list)

    logger.info(f"start file import handling for {len(db_objs)} files")

    return [db_obj.pk for db_obj in db_objs]
