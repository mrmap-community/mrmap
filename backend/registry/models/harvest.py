from datetime import datetime
from operator import mod

from celery import chord, group
from django.contrib.gis.db import models
from django.db import transaction
from django.db.models.query_utils import Q
from django.utils.translation import gettext_lazy as _
from eulxml import xmlmap
from registry.models.metadata import DatasetMetadata
from registry.models.service import CatalougeService
from registry.xmlmapper.iso_metadata.iso_metadata import \
    MdMetadata as XmlMdMetadata


class HarvestingJob(models.Model):
    """ helper model to visualize harvesting job workflow """
    service: CatalougeService = models.ForeignKey(
        to=CatalougeService,
        on_delete=models.CASCADE,
        verbose_name=_("service"),
        help_text=_("the csw for that this job is running"))
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
            get_hits_task, get_records_task)
        adding = self._state.adding
        super().save(*args, **kwargs)
        if adding:
            transaction.on_commit(
                lambda: get_hits_task.delay(harvesting_job_id=self.pk))
        elif self.total_records and not self.done_at:
            round_trips = (self.total_records // self.step_size)
            if self.total_records % self.step_size > 0:
                round_trips += 1
            tasks = []
            for number in range(1, round_trips + 1):
                tasks.append(get_records_task.s(
                    harvesting_job_id=self.pk, start_position=number * self.step_size))
            transaction.on_commit(lambda: group(tasks).apply_async())


def response_file_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT/xml_documents/<id>/<filename>
    return 'get_records_response/{0}/{1}'.format(instance.pk, filename)


class TemporaryMdMetadataFile(models.Model):
    job: HarvestingJob = models.ForeignKey(
        to=HarvestingJob,
        on_delete=models.CASCADE,
        verbose_name=_("harvesting job"))
    md_metadata_file: models.FileField = models.FileField(
        verbose_name=_("response"),
        help_text=_(
            "the content of the http response"),
        upload_to=response_file_path,
        editable=False)

    def save(self, *args, **kwargs) -> None:
        from registry.tasks.harvest import \
            temporary_md_metadata_file_to_db  # to avoid circular import errors
        adding = self._state.adding
        super().save(*args, **kwargs)
        if adding:
            transaction.on_commit(
                lambda: temporary_md_metadata_file_to_db.delay(md_metadata_file_id=self.pk))

    def md_metadata_file_to_db(self) -> DatasetMetadata:
        md_metadata: XmlMdMetadata = xmlmap.load_xmlobject_from_string(
            string=self.md_metadata_file,
            xmlclass=XmlMdMetadata)

        dataset_metadata, update, exists = DatasetMetadata.iso_metadata.update_or_create_from_parsed_metadata(
            parsed_metadata=md_metadata,
            related_object=self.job.service,
            origin_url=self.job.service.get_record_by_id_url(id=md_metadata.file_identifier))

        if exists and update:
            self.job.updated_records.add(dataset_metadata)
        elif exists and not update:
            self.job.existing_records.add(dataset_metadata)
        elif not exists:
            self.job.new_records.add(dataset_metadata)
        return dataset_metadata
