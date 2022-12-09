import os
from datetime import datetime
from typing import List

from celery import group
from django.contrib.gis.db import models
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models.fields.files import FieldFile
from django.db.models.query_utils import Q
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from eulxml import xmlmap
from ows_lib.xml_mapper.iso_metadata.iso_metadata import \
    MdMetadata as XmlMdMetadata
from ows_lib.xml_mapper.xml_responses.csw.get_records import GetRecordsResponse
from registry.managers.havesting import TemporaryMdMetadataFileManager
from registry.models.metadata import DatasetMetadata
from registry.models.service import CatalogueService
from requests import Response


class HarvestingJob(models.Model):
    """ helper model to visualize harvesting job workflow """
    service: CatalogueService = models.ForeignKey(
        to=CatalogueService,
        on_delete=models.CASCADE,
        verbose_name=_("service"),
        help_text=_("the csw for that this job is running"))
    record_type: str = models.CharField(
        max_length=10,
        default="dataset",
        choices=[("dataset", "dataset"), ("service", "service"),
                 ("tile", "tile"), ("series", "series")],
        verbose_name=_("record type"),
        help_text=_("the type of the record, which shall be harvested."))
    total_records: int = models.IntegerField(
        null=True,
        blank=True,
        editable=False,
        verbose_name=_("total records"),
        help_text=_("total count of records which will be harvested by this job"))
    step_size: int = models.IntegerField(
        default=50,
        blank=True)
    started_at: datetime = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        verbose_name=_("date started"),
        help_text=_("timestamp of start"))
    done_at: datetime = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        verbose_name=_("date done"),
        help_text=_("timestamp of done"))
    new_records = models.ManyToManyField(
        to=DatasetMetadata,
        related_name="harvested_by",
        editable=False,)
    existing_records = models.ManyToManyField(
        to=DatasetMetadata,
        related_name="ignored_by",
        editable=False,)
    updated_records = models.ManyToManyField(
        to=DatasetMetadata,
        related_name="updated_by",
        editable=False,)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['service', 'done_at'],
                                    name='%(app_label)s_%(class)s_service_done_at_uniq'),
            models.UniqueConstraint(fields=['service'],
                                    name='%(app_label)s_%(class)s_service_uniq',
                                    condition=Q(done_at__isnull=True))
        ]
        ordering = ['-done_at']
        get_latest_by = 'done_at'

    def save(self, *args, **kwargs) -> None:
        from registry.tasks.harvest import (  # to avoid circular import errors
            call_fetch_records, call_fetch_total_records)
        adding = self._state.adding
        ret = super().save(*args, **kwargs)

        # TODO: implement three phases:
        # 1. fetch total_records
        # 2. get statistic information about the average response duration with different step sizes
        # 3. start harvesting with the best average response duration step settings
        if adding:
            transaction.on_commit(
                lambda: call_fetch_total_records.delay(harvesting_job_id=self.pk))
        elif self.total_records and not self.done_at:
            round_trips = (self.total_records // self.step_size)
            if self.total_records % self.step_size > 0:
                round_trips += 1
            tasks = []
            for number in range(1, round_trips + 1):
                tasks.append(call_fetch_records.s(
                    harvesting_job_id=self.pk, start_position=number * self.step_size))
            transaction.on_commit(lambda: group(tasks).apply_async())
        return ret

    def fetch_total_records(self) -> int:
        client = self.service.client

        response: Response = client.send_request(
            request=client.prepare_get_records_request(
                xml_constraint=client.get_constraint(record_type=self.record_type)),
            timeout=60)

        get_records_response: GetRecordsResponse = xmlmap.load_xmlobject_from_string(string=response.content,
                                                                                     xmlclass=GetRecordsResponse)
        self.started_at = now()
        self.total_records = get_records_response.total_records
        self.save()
        return self.total_records

    def fetch_records(self, start_position) -> List[int]:
        client = self.service.client
        request = client.prepare_get_records_request(
            max_records=self.step_size,
            start_position=start_position,
            result_type="results",
            xml_constraint=client.get_constraint(record_type=self.record_type)
        )
        response: Response = client.send_request(
            request=request,
            timeout=60)

        get_records_response: GetRecordsResponse = xmlmap.load_xmlobject_from_string(string=response.content,
                                                                                     xmlclass=GetRecordsResponse)

        md_metadata: XmlMdMetadata
        db_md_metadata_file_list = []
        _counter = 0
        for md_metadata in get_records_response.gmd_records:
            db_md_metadata_file: TemporaryMdMetadataFile = TemporaryMdMetadataFile(
                job=self)
            # save the file without saving the instance in db... this will be done with bulk_create
            db_md_metadata_file.md_metadata_file.save(
                name=f"record_nr_{_counter + start_position}",
                content=ContentFile(content=md_metadata.serialize()),
                save=False)
            db_md_metadata_file_list.append(db_md_metadata_file)
            _counter += 1

        db_objs = TemporaryMdMetadataFile.objects.bulk_create_with_task_scheduling(
            objs=db_md_metadata_file_list)

        return [db_obj.pk for db_obj in db_objs]


def response_file_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT/xml_documents/<id>/<filename>
    return 'get_records_response/{0}/{1}'.format(instance.pk, filename)


class TemporaryMdMetadataFile(models.Model):
    job: HarvestingJob = models.ForeignKey(
        to=HarvestingJob,
        on_delete=models.CASCADE,
        verbose_name=_("harvesting job"))
    md_metadata_file: FieldFile = models.FileField(
        verbose_name=_("response"),
        help_text=_(
            "the content of the http response"),
        upload_to=response_file_path,
        editable=False)

    objects: TemporaryMdMetadataFileManager = TemporaryMdMetadataFileManager()

    def save(self, *args, **kwargs) -> None:
        from registry.tasks.harvest import \
            call_md_metadata_file_to_db  # to avoid circular import errors
        adding = self._state.adding
        super().save(*args, **kwargs)
        if adding:
            transaction.on_commit(
                lambda: call_md_metadata_file_to_db.delay(md_metadata_file_id=self.pk))

    def delete(self, *args, **kwargs):
        try:
            if os.path.isfile(self.md_metadata_file.path):
                os.remove(self.md_metadata_file.path)
        except (ValueError, FileNotFoundError):
            # filepath is broken
            pass
        super(TemporaryMdMetadataFile, self).delete(*args, **kwargs)

    def md_metadata_file_to_db(self) -> DatasetMetadata:
        _file: FieldFile = self.md_metadata_file.open()
        md_metadata: XmlMdMetadata = xmlmap.load_xmlobject_from_string(
            string=_file.read(),
            xmlclass=XmlMdMetadata)
        _file.close()

        dataset_metadata, update, exists = DatasetMetadata.iso_metadata.update_or_create_from_parsed_metadata(
            parsed_metadata=md_metadata,
            related_object=self.job.service,
            origin_url=self.job.service.client.prepare_get_record_by_id_request(id=md_metadata.file_identifier).url)

        if exists and update:
            self.job.updated_records.add(dataset_metadata)
        elif exists and not update:
            self.job.existing_records.add(dataset_metadata)
        elif not exists:
            self.job.new_records.add(dataset_metadata)

        if not TemporaryMdMetadataFile.objects.filter(job=self.job).exclude(pk=self.pk).exists():
            self.job.done_at = now()
            self.job.save()
        self.delete()
        return dataset_metadata
