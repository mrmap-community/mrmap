
import os
from os import walk

from celery import shared_task, states
from celery.utils.log import get_task_logger
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from eulxml import xmlmap
from lxml.etree import Error
from MrMap.settings import FILE_IMPORT_DIR
from notify.tasks import BackgroundProcessBased
from ows_lib.xml_mapper.iso_metadata.iso_metadata import WrappedIsoMetadata
from registry.models.harvest import HarvestingJob, TemporaryMdMetadataFile
from requests.exceptions import Timeout

logger = get_task_logger(__name__)


@shared_task(
    queue="default",
)
def create_harvesting_job(
    service_id,
    **kwargs  # to provide other kwargs which will be stored inside the TaskResult db objects
):
    return HarvestingJob.objects.create(service__pk=service_id)


@shared_task(
    bind=True,
    queue="default",
    autoretry_for=(Timeout,),
    retry_kwargs={'max_retries': 5},
    base=BackgroundProcessBased
)
def call_fetch_total_records(
    self,
    harvesting_job_id,
    **kwargs  # to provide other kwargs which will be stored inside the TaskResult db objects
):
    self.update_state(
        state=states.STARTED,
        meta={
            'done': 0,
            'total': 1,
            'phase': 'find out how many records the catalogue provides...'
        }
    )
    self.update_background_process()

    harvesting_job: HarvestingJob = HarvestingJob.objects.select_related("service").get(
        pk=harvesting_job_id)
    total_records = harvesting_job.fetch_total_records()

    self.update_state(
        state=states.SUCCESS,
        meta={
            'done': 1,
            'total': 1,
            'phase': f'catalogue provides {total_records} records.'
        }
    )
    self.update_background_process(
        phase=f'The catalogue provides {total_records} records. Harvesting is running...'  # noqa
    )

    return total_records


@shared_task(
    bind=True,
    queue="download",
    autoretry_for=(Timeout,),
    retry_kwargs={'max_retries': 5},
    base=BackgroundProcessBased
)
def call_fetch_records(
    self,
    harvesting_job_id,
    start_position,
    **kwargs  # to provide other kwargs which will be stored inside the TaskResult db objects
):
    harvesting_job: HarvestingJob = HarvestingJob.objects.select_related("service").get(
        pk=harvesting_job_id)

    self.update_state(
        state=states.STARTED,
        meta={
            'done': 0,
            'total': 1,
            'phase': f'fetching record {start_position} till {start_position + harvesting_job.service.max_step_size}.'
        }
    )
    self.update_background_process()

    fetched_records = harvesting_job.fetch_records(
        start_position=start_position)

    self.update_state(
        state=states.SUCCESS,
        meta={
            'done': 1,
            'total': 1,
            'phase': f'fetched {fetched_records.__len__()} records.'
        }
    )
    self.update_background_process(
        step_done=True
    )
    return fetched_records


@shared_task(
    bind=True,
    queue="db-routines",
    retry_kwargs={'max_retries': 5},
    base=BackgroundProcessBased
)
def call_md_metadata_file_to_db(
    self,
    md_metadata_file_id: int,
    **kwargs  # to provide other kwargs which will be stored inside the TaskResult db objects
):

    self.update_state(
        state=states.STARTED,
        meta={
            'done': 0,
            'total': 1,
            'phase': f'parse and store ISO Metadatarecord to db.'
        }
    )
    self.update_background_process()

    temporary_md_metadata_file: TemporaryMdMetadataFile = TemporaryMdMetadataFile.objects.get(
        pk=md_metadata_file_id)
    db_metadata, update, exists = temporary_md_metadata_file.md_metadata_file_to_db()

    is_new = not exists and not update
    is_updated = not is_new and update

    if is_updated:
        action = "updated"
    elif is_new:
        action = "new"
    else:
        action = "keeped as it is"

    self.update_state(
        state=states.SUCCESS,
        meta={
            'done': 1,
            'total': 1,
            'phase': f'{action} {type(db_metadata)} {db_metadata.pk}.'
        }
    )
    self.update_background_process(
        step_done=True
    )

    return db_metadata.pk


@shared_task(
    queue="db-routines",
)
def check_for_files_to_import(
    **kwargs  # to provide other kwargs which will be stored inside the TaskResult db objects
):
    # TODO: create backgroundprocess object to track this processing

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
