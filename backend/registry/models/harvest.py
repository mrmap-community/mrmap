import json
import os
import sys
from uuid import uuid4

from celery import chord
from django.contrib.auth import get_user_model
from django.contrib.gis.db import models
from django.contrib.postgres.fields import ArrayField
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.db.models import UniqueConstraint
from django.db.models.fields.files import FieldFile
from django.db.models.query_utils import Q
from django.utils import timezone
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_celery_beat.models import PeriodicTask
from eulxml import xmlmap
from extras.models import AdditionalTimeFieldsHistoricalModel
from lxml.etree import XML, XMLParser
from MrMap.celery import app
from ows_lib.xml_mapper.iso_metadata.iso_metadata import \
    MdMetadata as XmlMdMetadata
from ows_lib.xml_mapper.xml_responses.csw.get_records import GetRecordsResponse
from registry.enums.harvesting import (CollectingStatenEnum,
                                       HarvestingPhaseEnum, LogKindEnum,
                                       LogLevelEnum)
from registry.enums.metadata import MetadataOriginEnum
from registry.exceptions.harvesting import InternalServerError
from registry.managers.havesting import (HarvestedMetadataRelationQuerySet,
                                         HarvestingJobManager,
                                         TemporaryMdMetadataFileManager)
from registry.models.metadata import (DatasetMetadataRecord,
                                      ServiceMetadataRecord)
from registry.models.service import CatalogueService
from registry.tasks.harvest import call_chord_md_metadata_file_to_db
from requests import Response
from simple_history.models import HistoricalRecords
from simple_history.utils import update_change_reason


class ProcessingData(models.Model):
    phase = models.CharField(
        max_length=512,
        verbose_name=_('phase'),
        help_text=_('Current phase of the process'))
    date_created = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Created DateTime'),
        help_text=_('Datetime field when the process was created in UTC'),
        null=True,
        blank=True)
    done_at = models.DateTimeField(
        verbose_name=_('Completed DateTime'),
        help_text=_('Datetime field when the process was completed in UTC'),
        null=True,
        blank=True,
        editable=False)
    celery_task_ids = ArrayField(
        models.UUIDField(),
        default=list,
        blank=True,
        editable=False)

    class Meta:
        abstract = True
        ordering = ["-date_created"]
        get_latest_by = "-date_created"
        indexes = [
            models.Index(fields=["date_created"]),
            models.Index(fields=["done_at"]),
        ]
        constraints = []

    def abort(self):
        self.phase = HarvestingPhaseEnum.ABORTED.value
        self.done_at = now()
        # From celery notes https://docs.celeryq.dev/en/latest/userguide/workers.html#revoke-by-stamped-headers-revoking-tasks-by-their-stamped-headers
        # Warning:
        # The revoked headers mapping is not persistent across restarts,
        # so if you restart the workers, the revoked headers will be lost and need to be mapped again.
        app.control.revoke(
            [str(_id) for _id in self.celery_task_ids],
            terminate=True
        )
        # Another option would be to call the `app.control.revoke(related_task_ids, terminate=True)`,
        # but there will be a memory limit which is 50000 by default.
        # But Harvesting jobs can have a way far more tasks that are currently in the queue.
        # BKG csw for example provides more than 600000 records. So there will be minimum that number of tasks in the queue.
        #
        # From celery notes https://docs.celeryq.dev/en/latest/userguide/workers.html#revoke-revoking-tasks
        # Note:
        # The maximum number of revoked tasks to keep in memory can be specified using the
        # CELERY_WORKER_REVOKES_MAX environment variable, which defaults to 50000.

    def append_celery_task_ids(self, ids):
        """thread safe append function"""
        self._meta.model.objects.filter(pk=self.pk).select_for_update().update(
            celery_task_ids=self.celery_task_ids + ids
        )


class HarvestedMetadataRelation(AdditionalTimeFieldsHistoricalModel):
    harvesting_job = models.ForeignKey(
        to="registry.HarvestingJob",
        on_delete=models.CASCADE,
        related_name="harvested_metadata_relations",
        related_query_name="harvested_metadata_relation")
    dataset_metadata_record = models.ForeignKey(to="registry.DatasetMetadataRecord",
                                                on_delete=models.CASCADE,
                                                null=True,
                                                related_name="harvested_dataset_metadata_relations",
                                                related_query_name="harvested_dataset_metadata_relation")
    service_metadata_record = models.ForeignKey(to="registry.ServiceMetadataRecord",
                                                on_delete=models.CASCADE,
                                                null=True,
                                                related_name="harvested_service_metadata_relations",
                                                related_query_name="harvested_service_metadata_relation")
    collecting_state = models.PositiveSmallIntegerField(
        choices=CollectingStatenEnum.choices)
    download_duration = models.DurationField(
        null=True,
        blank=True,
        verbose_name=_("download duration"),
        help_text=_("This is the duration it tooked proportionately to download this record. "
                    "This means if the GetRecords response contains 50 records for example, the request duration was 50 * self.download_duration"
                    "To get the download duration over all for one harvesting job, aggregate this col."))
    processing_duration = models.DurationField(
        null=True,
        blank=True,
        verbose_name=_("processing duration"),
        help_text=_("This is the duration it tooked to handle the processing of creating or updating this record."))
    history_date = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Created DateTime'),
        help_text=_('Datetime field when the relation was created'),
    )

    objects = HarvestedMetadataRelationQuerySet.as_manager()

    class Meta:
        indexes = [
            models.Index(
                fields=["harvesting_job", "dataset_metadata_record"]),
            models.Index(
                fields=["harvesting_job", "dataset_metadata_record", "collecting_state"]),
            models.Index(
                fields=["harvesting_job", "service_metadata_record"]),
            models.Index(
                fields=["harvesting_job", "service_metadata_record", "collecting_state"]),
            models.Index(
                fields=["harvesting_job", "id"]),
        ]
        constraints = [
            models.CheckConstraint(
                name="dm_record_or_sm_record",
                condition=(
                    Q(dataset_metadata_record__isnull=True, service_metadata_record__isnull=False) |
                    Q(dataset_metadata_record__isnull=False, service_metadata_record__isnull=True)),
                violation_error_message="wrong relation type. dataset_metadata_record or service_metadata_record, not both is required."
            ),
            models.UniqueConstraint(
                name="atomic_new_updated_or_exsisting_collecting_state_for_dm_record",
                fields=["harvesting_job",
                        "dataset_metadata_record",
                        "collecting_state"],
                # new, updated, existing can only be set one time per harvesting job.
                # IF one of this states are set, for an existing record, it is deliverd multiple times by the remote service.
                # To support analyzing this failure behaviour of remote services,
                # we support storing collecting_state="duplicated" multiple times per harvesting job
                condition=~Q(
                    collecting_state=CollectingStatenEnum.DUPLICATED.value)
            ),
            models.UniqueConstraint(
                name="atomic_new_updated_or_exsisting_collecting_state_for_sm_record",
                fields=["harvesting_job",
                        "service_metadata_record",
                        "collecting_state"],
                # new, updated, existing can only be set one time per harvesting job.
                # IF one of this states are set, for an existing record, it is deliverd multiple times by the remote service.
                # To support analyzing this failure behaviour of remote services,
                # we support storing collecting_state="duplicated" multiple times per harvesting job
                condition=~Q(
                    collecting_state=CollectingStatenEnum.DUPLICATED.value)
            )
        ]


class HarvestingJob(ProcessingData):
    """ helper model to visualize harvesting job workflow """
    service: CatalogueService = models.ForeignKey(
        to=CatalogueService,
        on_delete=models.CASCADE,
        null=True,  # possible for file import jobs
        verbose_name=_("service"),
        help_text=_("the csw for that this job is running"),
        related_name="harvesting_jobs",
        related_query_name="harvesting_job")
    max_step_size = models.PositiveSmallIntegerField(
        verbose_name=_("max step size"),
        help_text=_(
            "the maximum step size this csw can handle by a single GetRecords request."),
        default=50)
    harvest_datasets = models.BooleanField(default=True)
    harvest_services = models.BooleanField(default=True)
    total_records: int = models.PositiveIntegerField(
        null=True,
        blank=True,
        editable=False,
        verbose_name=_("total records"),
        help_text=_("total count of records which will be harvested by this job"))
    harvested_dataset_metadata = models.ManyToManyField(
        to=DatasetMetadataRecord,
        through=HarvestedMetadataRelation,
        related_name="harvesting_jobs",
        related_query_name="harvesting_job",
        editable=False,
        blank=True)
    harvested_service_metadata = models.ManyToManyField(
        to=ServiceMetadataRecord,
        through=HarvestedMetadataRelation,
        related_name="harvesting_jobs",
        related_query_name="harvesting_job",
        editable=False,
        blank=True)
    phase = models.PositiveSmallIntegerField(
        verbose_name=_('phase'),
        help_text=_('Current phase of the process'),
        choices=HarvestingPhaseEnum,
        default=HarvestingPhaseEnum.PENDING.value,
        blank=True,
    )
    log_level = models.PositiveSmallIntegerField(
        choices=LogLevelEnum,
        default=LogLevelEnum.INFO,
        blank=True
    )
    change_log = HistoricalRecords(
        related_name="change_logs",
        bases=[AdditionalTimeFieldsHistoricalModel,],
    )

    objects = HarvestingJobManager()

    class Meta(ProcessingData.Meta):
        verbose_name = _("Harvesting Job")
        verbose_name_plural = _("Harvesting Jobs")
        ordering = ProcessingData.Meta.ordering
        get_latest_by = ProcessingData.Meta.get_latest_by
        indexes = ProcessingData.Meta.indexes
        constraints = ProcessingData.Meta.constraints + [
            UniqueConstraint(
                fields=["service"],
                condition=Q(done_at__isnull=True),
                name="only_one_unfinished_job_per_service",
                violation_error_message=_(
                    "There is an existing noncompleted job for this service.")
            )
        ]

    def log(self,
            description,
            extented_description=None,
            level=LogLevelEnum.INFO.value,
            kind=None
            ):
        if level <= self.log_level:
            log_obj = HarvestingLog(
                harvesting_job=self,
                level=level,
                kind=kind,
                description=description,
            )
            if extented_description:
                log_obj.extented_description.save(
                    name=f"{uuid4()}.txt",
                    content=ContentFile(content=extented_description))
            else:
                log_obj.save()
            return log_obj

    def add_harvested_metadata_relation(
            self,
            md_metadata,
            related_object,
            collecting_state,
            download_duration,
            processing_duration):
        model = HarvestedMetadataRelation
        kwargs = {"service_metadata_record": related_object,
                  "harvesting_job": self,
                  "collecting_state": collecting_state,
                  "download_duration": download_duration,
                  "processing_duration": processing_duration}
        if md_metadata.is_dataset:
            kwargs.pop("service_metadata_record")
            kwargs.update({"dataset_metadata_record": related_object})
        try:
            return model.objects.create(**kwargs)
        except IntegrityError as e:
            if "unique constraint" in str(e.args).lower():
                kwargs.update(
                    {"collecting_state": CollectingStatenEnum.DUPLICATED.value})
                db_obj = model.objects.create(**kwargs)
                return db_obj

    def handle_adding(self, *args, **kwargs):
        # atomic block is needed. Otherwise the on_commit() will fire immediately:
        # see docs: https://docs.djangoproject.com/en/5.1/topics/db/transactions/#timing-of-execution
        with transaction.atomic():
            from registry.tasks.harvest import \
                call_fetch_total_records  # to avoid circular import errors

            # save to get the id of the object
            ret = super(HarvestingJob, self).save(*args, **kwargs)

            task_id = uuid4()
            task = call_fetch_total_records.s(
                harvesting_job_id=self.pk,
                http_request=self._http_request()
            )
            task.set(task_id=str(task_id))
            self.append_celery_task_ids([task_id])

            transaction.on_commit(func=lambda: task.apply_async())
            return ret

    def handle_total_records_defined(self):
        """total records is known now. Calculate roundtrips and start parallel harvesting tasks"""
        with transaction.atomic():
            self.phase = HarvestingPhaseEnum.DOWNLOAD_RECORDS.value

            round_trips = (self.total_records //
                           self.max_step_size)
            round_trips += 1 if self.total_records % self.max_step_size > 0 else 0

            from registry.tasks.harvest import \
                call_fetch_records  # to avoid circular import errors
            task_ids = []
            tasks = []
            for number in range(0, round_trips):
                task_id = uuid4()
                task = call_fetch_records.s(
                    harvesting_job_id=self.pk,
                    start_position=number * self.max_step_size + 1,
                    http_request=self._http_request()
                )
                task.set(task_id=str(task_id))
                task_ids.append(task_id)
                tasks.append(task)

            callback_id = uuid4()
            callback = call_chord_md_metadata_file_to_db.s(
                harvesting_job_id=str(self.pk),
                http_request=self._http_request(),
            )
            callback.set(task_id=str(callback_id))

            self.append_celery_task_ids(task_ids + [callback_id])

            # publishing tasks on commit was successfully
            transaction.on_commit(lambda: chord(tasks, callback)())

        self.log(
            description=f"phase {HarvestingPhaseEnum.DOWNLOAD_RECORDS.value} started. {round_trips} round trips with step size {self.max_step_size} are needed."
        )

    # TODO: implement three phases:
    # 1. fetch total_records
    # 2. get statistic information about the average response duration with different step sizes
    # 3. start harvesting with the best average response duration step settings

    def save(self, skip_history_when_saving=True, *args, **kwargs):
        if self._state.adding and self.service:
            return self.handle_adding(*args, **kwargs)
        elif self.total_records == 0:
            # error case. CSW does not provide records for our default request behaviour.
            self.done_at = now()
            self.phase = HarvestingPhaseEnum.COMPLETED.value
            return super(HarvestingJob, self).save(*args, **kwargs)
        elif self.phase == HarvestingPhaseEnum.ABORT.value:
            self.abort()
            self.phase = HarvestingPhaseEnum.ABORTED.value
            self.done_at = now()
            return super(HarvestingJob, self).save(*args, **kwargs)

        # see docs of django-simple-history
        # https://django-simple-history.readthedocs.io/en/latest/querying_history.html#save-without-creating-historical-records
        # we only create a record by default for creating objects.
        self.skip_history_when_saving = skip_history_when_saving

        ret = super(HarvestingJob, self).save(*args, **kwargs)
        del self.skip_history_when_saving
        return ret

    def _http_request(self):
        if self.service:
            first_history = self.change_log.first()
            created_by = first_history.history_user if first_history else None
            return {
                "path": "somepath",
                "method": "GET",
                "content_type": "application/json",
                "data": {},
                "user_pk": created_by.pk
            } if created_by else None
        else:
            return {
                "path": "somepath",
                "method": "GET",
                "content_type": "application/json",
                "data": {},
                "user_pk": get_user_model().objects.get(username="mrmap").pk
            }

    def get_record_types(self):
        record_types = []
        if self.harvest_datasets:
            record_types.append("dataset")
        if self.harvest_services:
            record_types.append("service")
        return record_types

    def fetch_total_records(self) -> int:
        client = self.service.client

        first_response: Response = client.send_request(
            request=client.get_records_request(
                xml_constraint=client.get_constraint(record_types=self.get_record_types())),
            timeout=60)

        if self._check_xml_response(first_response):
            self._log_response_error(response=first_response)
            self.total_records = 0
            self.save()
            return self.total_records

        get_records_response: GetRecordsResponse = xmlmap.load_xmlobject_from_string(string=first_response.content,
                                                                                     xmlclass=GetRecordsResponse)
        self.total_records = get_records_response.total_records
        if not self.total_records:
            # try again, cause some csw server implementations are broken and don't support our default TypeName query param
            second_response: Response = client.send_request(
                request=client.get_records_request(
                    type_names="csw:Record",
                    xml_constraint=client.get_constraint(record_types=self.get_record_types())),
                timeout=60)

            if self._check_xml_response(first_response):
                self._log_response_error(response=second_response)
                self.total_records = 0
                self.save()
                return self.total_records

            get_records_response: GetRecordsResponse = xmlmap.load_xmlobject_from_string(string=second_response.content,
                                                                                         xmlclass=GetRecordsResponse)

            self.total_records = get_records_response.total_records

            if not self.total_records:
                # terminate celery workflow by returning total records = 0
                self.total_records = 0

                extended_description = f"Can't get total records from remote service by requesting {second_response.request.url} url. \n"
                extended_description += f"http status code: {second_response.status_code}\n"
                extended_description += f"response:\n{second_response.text}"
                kind = LogKindEnum.REMOTE_ERROR.value if second_response.status_code >= 500 else None

                self.log(
                    description="GetTotalRecords failed",
                    extented_description=extended_description,
                    level=LogLevelEnum.ERROR.value,
                    kind=kind,
                )

        self.save()
        return self.total_records

    def _log_response_error(self, response):
        extented_description = {
            "url": response.request.url,
            "status_code": response.status_code,
            "content": response.content
        }
        self.log(
            level=LogLevelEnum.ERROR.value,
            kind=LogKindEnum.REMOTE_ERROR.value,
            description="Response Error",
            extented_description=str(extented_description),
        )

    def _check_xml_is_parseable(self, xml: str) -> bool:
        try:
            XML(xml, XMLParser())
        except:
            return False
        return True

    def _check_xml_response(self, response):
        if not response.ok or not self._check_xml_is_parseable(response.content) or "<ExceptionReport" in response.text:
            self._log_response_error(response=response)
            if response.status_code >= 500 <= 600:
                raise InternalServerError
            return True
        return False

    def fetch_records(self, start_position) -> int | None:
        client = self.service.client
        request = client.get_records_request(
            max_records=self.max_step_size,
            start_position=start_position,
            result_type="results",
            xml_constraint=client.get_constraint(
                record_types=self.get_record_types())
        )
        datestamp = timezone.now()
        response: Response = client.send_request(
            request=request,
            timeout=60)

        if self._check_xml_response(response):
            self._log_response_error(response=response)
            return

        get_records_response: GetRecordsResponse = xmlmap.load_xmlobject_from_string(string=response.content,
                                                                                     xmlclass=GetRecordsResponse)

        md_metadata: XmlMdMetadata
        db_md_metadata_file_list = []
        records_count = len(get_records_response.gmd_records)

        for idx, md_metadata in enumerate(get_records_response.gmd_records):
            db_md_metadata_file: TemporaryMdMetadataFile = TemporaryMdMetadataFile(
                job=self,
                request_id=datestamp,
                requested_url=response.url,
                download_duration=response.elapsed / records_count
            )
            # save the file without saving the instance in db... this will be done with bulk_create
            db_md_metadata_file.md_metadata_file.save(
                name=f"record_nr_{idx + start_position}",
                content=ContentFile(content=md_metadata.serialize()),
                save=False)
            db_md_metadata_file_list.append(db_md_metadata_file)

        db_objs = TemporaryMdMetadataFile.objects.bulk_create(
            objs=db_md_metadata_file_list)

        should_return_count = self.max_step_size if start_position + \
            self.max_step_size < self.total_records else self.total_records - start_position

        if len(db_objs) < should_return_count:
            self.log(
                level=LogLevelEnum.WARNING.value,
                kind=LogKindEnum.COUNT_MISSMATCH.value,
                description=f"Only {len(db_objs)} received from {should_return_count} possible records.\n" +
                f"URL: {request.url}"
            )

        return len(db_objs)


def response_file_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT/xml_documents/<job_id>/<filename>
    return f'temporary_md_metadata_file/{instance.job_id}/{filename}'


class TemporaryMdMetadataFile(models.Model):
    """This are the unhalded records."""
    job: HarvestingJob = models.ForeignKey(
        to=HarvestingJob,
        on_delete=models.CASCADE,
        verbose_name=_("harvesting job"),
        null=True,
        related_name="temporary_md_metadata_files",
        related_query_name="temporary_md_metadata_file")
    md_metadata_file: FieldFile = models.FileField(
        verbose_name=_("response"),
        help_text=_(
            "the content of the http response, or of the imported file"),
        upload_to=response_file_path)
    re_schedule = models.BooleanField(
        default=False,
        help_text=_("to re run to db task"))
    has_import_error = models.BooleanField(
        default=False,
        editable=False,
        help_text=_("signals if this object can't be imported")
    )
    import_error = models.TextField(
        verbose_name=_("import error"),
        help_text=_("raised error while importing"),
        default="",
        blank=True)
    request_id = models.DateTimeField(null=True)
    requested_url = models.URLField(
        max_length=4096,
        null=True)
    download_duration = models.DurationField(
        null=True,
        blank=True,
        verbose_name=_("download duration"),
        help_text=_("This is the duration it tooked proportionately to download this record. "
                    "This means if the GetRecords response contains 50 records for example, "
                    "the request duration was 50 * self.download_duration"))

    objects: TemporaryMdMetadataFileManager = TemporaryMdMetadataFileManager()

    class Meta:
        indexes = [
            models.Index(
                fields=["job_id", "-id"]),
        ]

    def save(self, *args, **kwargs) -> None:
        from registry.tasks.harvest import \
            call_md_metadata_file_to_db  # to avoid circular import errors
        adding = self._state.adding or self.re_schedule
        self.re_schedule = False

        ret = super().save(*args, **kwargs)

        if adding:
            task_id = uuid4()

            task = call_md_metadata_file_to_db.delay(
                md_metadata_file_id=self.pk,
                harvesting_job_id=self.job.pk,  # to provide the job id for TaskResult db objects
                http_request=self.job._http_request(),
            )
            task.set(task_id=str(task_id))

            self.job.append_celery_task_ids([task_id])

            transaction.on_commit(lambda: task.apply_async())
        return ret

    def delete(self, *args, **kwargs):
        try:
            if os.path.isfile(self.md_metadata_file.path):
                os.remove(self.md_metadata_file.path)
        except (ValueError, FileNotFoundError):
            # filepath is broken
            pass
        return super(TemporaryMdMetadataFile, self).delete(*args, **kwargs)

    def md_metadata_file_to_db(self):

        with self.md_metadata_file.open('r') as _file:

            md_metadata: XmlMdMetadata = xmlmap.load_xmlobject_from_string(
                string=_file.read(),
                xmlclass=XmlMdMetadata)
            try:
                db_metadata = None
                update_or_create_kwargs = {
                    'parsed_metadata': md_metadata,
                    'origin': MetadataOriginEnum.CATALOGUE.value if self.job.service_id else MetadataOriginEnum.FILE_SYSTEM_IMPORT.value,
                    'origin_url': self.job.service.client.get_record_by_id_request(id=md_metadata.file_identifier).url if self.job.service_id else "http://localhost"
                }
                start_db_processing = now()
                if md_metadata.is_service:
                    db_metadata, update, exists = ServiceMetadataRecord.iso_metadata.update_or_create_from_parsed_metadata(
                        **update_or_create_kwargs)
                elif md_metadata.is_dataset:
                    db_metadata, update, exists = DatasetMetadataRecord.iso_metadata.update_or_create_from_parsed_metadata(
                        **update_or_create_kwargs)
                else:
                    raise NotImplementedError(
                        f"file is neither service nor dataset record. HierarchyLevel: {md_metadata._hierarchy_level}")
                if db_metadata:
                    if self.job:
                        end_db_processing = now()
                        relation = self.update_relations(
                            md_metadata,
                            exists,
                            update,
                            db_metadata,
                            end_db_processing - start_db_processing
                        )
                        if relation.collecting_state == CollectingStatenEnum.DUPLICATED.value:
                            # do not delete this entries for analyze purposes
                            import_error = {
                                "reason": "duplicated",
                                "db_metadata.pk": db_metadata.pk,
                                "db_metadata.file_identifier": db_metadata.file_identifier,
                                "db_metadata.code_space": db_metadata.code_space,
                                "db_metadata.code": db_metadata.code,
                                "md_metadata.file_identifier": md_metadata.file_identifier,
                                "md_metadata.code": md_metadata.code,
                                "md_metadata.code_space": md_metadata.code_space
                            }
                            self.has_import_error = True
                            self.import_error = str(import_error)
                            self.save()
                            return db_metadata, update, exists
                        elif update or not exists:
                            # something has changed... so tell us from what service this changes come from
                            update_change_reason(
                                db_metadata,
                                'fileimport'if self.job.service is None else f'csw:{self.job.service}'
                            )

                    self.delete()

                    return db_metadata, update, exists
            except Exception as e:
                import traceback
                exc_info = sys.exc_info()
                self.import_error = ''.join(
                    traceback.format_exception(*exc_info))
                self.has_import_error = True
                self.save()
                raise e

    def update_relations(self, md_metadata, exists, update, db_metadata, duration):
        # TODO: is this relation still needed? Or is it enough to collect the harvested through by the harvested_metadata_relations?
        if self.job.service:
            db_metadata.harvested_through.add(self.job.service)

        collecting_state = CollectingStatenEnum.UPDATED.value if exists and update else CollectingStatenEnum.EXISTING.value if exists and not update else CollectingStatenEnum.NEW.value
        return self.job.add_harvested_metadata_relation(
            md_metadata,
            db_metadata,
            collecting_state,
            self.download_duration,
            duration)


def extented_description_file_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT/xml_documents/<job_id>/<filename>
    return f'HarvestingLog/{instance.harvesting_job}/{filename}'


class HarvestingLog(models.Model):
    harvesting_job = models.ForeignKey(
        to=HarvestingJob,
        on_delete=models.CASCADE,
        related_name='logs',
        related_query_name='log'
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Created DateTime'),
        help_text=_('Datetime field when the task result was created in UTC')
    )
    level = models.PositiveSmallIntegerField(
        choices=LogLevelEnum,
        default=LogLevelEnum.INFO.value,
        blank=True,
    )
    kind = models.PositiveSmallIntegerField(
        choices=LogKindEnum.choices,
        blank=True,
        null=True,
    )
    description = models.CharField(
        max_length=512,
        default="",
        verbose_name=_('Description'),
        blank=True,
    )
    extented_description = models.FileField(
        null=True,
        verbose_name=_("Extented Description"),
        help_text=_("this can be the response content for example"),
        upload_to=extented_description_file_path)


class PeriodicHarvestingJob(PeriodicTask):
    service: CatalogueService = models.ForeignKey(
        to=CatalogueService,
        on_delete=models.CASCADE,
        related_name="periodic_harvesting_jobs",
        related_query_name="periodic_harvesting_job",
        verbose_name=_("catalogue service"),
        help_text=_("this is the service which shall be harvested"))

    def __init__(self, *args, **kwargs) -> None:
        # TODO: move to save(), cause init will manipulate the object we will see on django-admin interface etc.
        super().__init__(*args, **kwargs)
        if not self.pk and not self.name:
            # we do not need this field now... just generate random data
            self.name = uuid4()
        if not self.pk and not self.task:
            self.task = "registry.tasks.harvest.create_harvesting_job"
        if not self.pk and self.kwargs and "service_id" not in self.kwargs:
            self.kwargs = {
                "service_id": str(self.service.pk)
            }
        if not self.pk and not self.queue:
            self.queue = "default"

        system_user, _ = get_user_model().objects.get_or_create(username="system")
        http_request = {
            "path": "/periodic-harvesting-job",
            "method": "GET",
            "content_type": "application/json",
            "data": {},
            "user_pk": system_user.pk
        }
        if isinstance(self.kwargs, str):
            self.kwargs = json.loads(self.kwargs)
            self.kwargs.update({
                "http_request": http_request,
            })

    class Meta:
        verbose_name = _('Periodic Harvesting Job')
        verbose_name_plural = _('Periodic Harvesting Jobs')
