import os
import sys
from uuid import uuid4

from celery import chord
from django.contrib.gis.db import models
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.db.models.fields.files import FieldFile
from django.db.models.query_utils import Q
from django.utils import timezone
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from eulxml import xmlmap
from lxml.etree import XML, XMLParser
from notify.enums import LogTypeEnum, ProcessNameEnum
from notify.models import BackgroundProcess, BackgroundProcessLog
from ows_lib.xml_mapper.iso_metadata.iso_metadata import \
    MdMetadata as XmlMdMetadata
from ows_lib.xml_mapper.xml_responses.csw.get_records import GetRecordsResponse
from registry.enums.harvesting import CollectingStatenEnum
from registry.enums.metadata import MetadataOriginEnum
from registry.exceptions.harvesting import InternalServerError
from registry.managers.havesting import (HarvestingJobManager,
                                         TemporaryMdMetadataFileManager)
from registry.models.metadata import (DatasetMetadataRecord,
                                      ServiceMetadataRecord)
from registry.models.service import CatalogueService
from registry.tasks.harvest import call_chord_md_metadata_file_to_db
from requests import Response
from simple_history.models import HistoricalRecords


class HarvestedMetadataRelation(models.Model):
    harvesting_job = models.ForeignKey(
        to="registry.HarvestingJob",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)ss",
        related_query_name="%(app_label)s_%(class)s")
    collecting_state = models.CharField(
        max_length=10,
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

    class Meta:
        abstract = True


class HarvestedDatasetMetadataRelation(HarvestedMetadataRelation):
    dataset_metadata_record = models.ForeignKey(to="registry.DatasetMetadataRecord",
                                                on_delete=models.CASCADE,
                                                related_name="harvested_dataset_metadata_relations",
                                                related_query_name="harvested_dataset_metadata_relation")

    class Meta:
        indexes = [
            models.Index(fields=["harvesting_job", "dataset_metadata_record"]),
            models.Index(
                fields=["harvesting_job", "dataset_metadata_record", "collecting_state"]),
        ]
        constraints = [
            models.UniqueConstraint(
                name="%(app_label)s_%(class)s_atomic_new_updated_or_exsisting_collecting_state",
                fields=["harvesting_job",
                        "dataset_metadata_record",
                        "collecting_state"],
                # new, updated, existing can only be set one time per harvesting job.
                # IF one of this states are set, for an existing record, it is deliverd multiple times by the remote service.
                # To support analyzing this failure behaviour of remote services,
                # we support storing collecting_state="duplicated" multiple times per harvesting job
                condition=~Q(
                    collecting_state=CollectingStatenEnum.DUPLICATED.value)
            )
        ]


class HarvestedServiceMetadataRelation(HarvestedMetadataRelation):
    service_metadata_record = models.ForeignKey(to="registry.ServiceMetadataRecord",
                                                on_delete=models.CASCADE,
                                                related_name="harvested_service_metadata_relations",
                                                related_query_name="harvested_service_metadata_relation")

    class Meta:
        indexes = [
            models.Index(fields=["harvesting_job", "service_metadata_record"]),
            models.Index(
                fields=["harvesting_job", "service_metadata_record", "collecting_state"]),

        ]
        constraints = [
            models.UniqueConstraint(
                name="%(app_label)s_%(class)s_atomic_new_updated_or_exsisting_collecting_state",
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


class HarvestingJob(models.Model):
    """ helper model to visualize harvesting job workflow """
    service: CatalogueService = models.ForeignKey(
        to=CatalogueService,
        on_delete=models.CASCADE,
        verbose_name=_("service"),
        help_text=_("the csw for that this job is running"),
        related_name="harvesting_jobs",
        related_query_name="harvesting_job")
    max_step_size = models.IntegerField(
        verbose_name=_("max step size"),
        help_text=_(
            "the maximum step size this csw can handle by a single GetRecords request."),
        default=50)
    background_process = models.ForeignKey(
        to=BackgroundProcess,
        on_delete=models.PROTECT,
        editable=False,)
    harvest_datasets = models.BooleanField(default=True)
    harvest_services = models.BooleanField(default=True)

    total_records: int = models.IntegerField(
        null=True,
        blank=True,
        editable=False,
        verbose_name=_("total records"),
        help_text=_("total count of records which will be harvested by this job"))
    harvested_dataset_metadata = models.ManyToManyField(
        to=DatasetMetadataRecord,
        through=HarvestedDatasetMetadataRelation,
        related_name="harvesting_jobs",
        related_query_name="harvesting_job",
        editable=False,
        blank=True)
    harvested_service_metadata = models.ManyToManyField(
        to=ServiceMetadataRecord,
        through=HarvestedServiceMetadataRelation,
        related_name="harvesting_jobs",
        related_query_name="harvesting_job",
        editable=False,
        blank=True)

    change_log = HistoricalRecords(
        related_name="change_logs",
    )

    objects = HarvestingJobManager()

    def add_harvested_metadata_relation(
            self,
            md_metadata,
            related_object,
            collecting_state,
            download_duration,
            processing_duration):
        model = HarvestedServiceMetadataRelation
        kwargs = {"service_metadata_record": related_object,
                  "harvesting_job": self,
                  "collecting_state": collecting_state,
                  "download_duration": download_duration,
                  "processing_duration": processing_duration}
        if md_metadata.is_dataset:
            model = HarvestedDatasetMetadataRelation
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
            self.background_process = BackgroundProcess.objects.create(
                phase="Get total records of the catalogue",
                process_type=ProcessNameEnum.HARVESTING.value,
                description=f'Harvesting job for service {self.service.pk}',
                service=self.service
            )
            # save to get the id of the object
            ret = super(HarvestingJob, self).save(*args, **kwargs)

            task_id = uuid4()
            task = call_fetch_total_records.s(
                harvesting_job_id=self.pk,
                http_request=self._http_request(),
                background_process_pk=self.background_process_id
            )
            task.set(task_id=str(task_id))

            self.background_process.celery_task_ids.append(task_id)
            self.background_process.save()

            transaction.on_commit(func=lambda: task.apply_async())
            return ret

    def handle_total_records_defined(self):
        """total records is known now. Calculate roundtrips and start parallel harvesting tasks"""
        with transaction.atomic():
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
                    http_request=self._http_request(),
                    background_process_pk=self.background_process_id,
                )
                task.set(task_id=str(task_id))
                task_ids.append(task_id)
                tasks.append(task)

            callback_id = uuid4()
            task_ids.append(callback_id)

            # TODO: how to set and get task_id for all callbacks?
            callback = call_chord_md_metadata_file_to_db.s(
                harvesting_job_id=self.pk,
                http_request=self._http_request(),
                background_process_pk=self.background_process_id
            )
            callback.set(task_id=str(callback_id))

            # publishing tasks on commit was successfully
            transaction.on_commit(lambda: chord(tasks)(callback))

        """calculate the potential max tasks which can results from the precalculation of roundtrips and total_records.
            The calculation is not bullet proof. The CSW can response for example with 100000 total records. 
            The processing of harvesting can take a long time, in that the catalogue can changes his content. 
            So it can be 1000010 records or 99980 or something else. 
            The state of the remote CSW is not freezed after the first total_records call is done.

            An other fact is, that the get records request can response with currupt metadata records, which we can't handle.
            In that case, no TemporaryMdMetadataFile object is created and no call_md_metadata_file_to_db task is created.
        """
        total_steps = tasks.__len__()  # how many call_fetch_records task will be run
        total_steps += self.total_records

        bp = self.background_process
        bp.total_steps = total_steps
        bp.celery_task_ids.extend(task_ids)
        bp.save()

        BackgroundProcessLog.objects.create(
            background_process=bp,
            log_type=LogTypeEnum.INFO,
            description=f"call_chord_md_metadata_file_to_db called. {round_trips} round trips with step size {self.max_step_size} are needed."
        )

    # TODO: implement three phases:
    # 1. fetch total_records
    # 2. get statistic information about the average response duration with different step sizes
    # 3. start harvesting with the best average response duration step settings

    def save(self, *args, **kwargs):
        if self._state.adding:
            return self.handle_adding(*args, **kwargs)
        elif self.total_records == 0:
            # error case. CSW does not provide records for our default request behaviour.
            self.background_process.done_at = now()

        return super(HarvestingJob, self).save(*args, **kwargs)

    def _http_request(self):
        first_history = self.change_log.first()
        created_by = first_history.history_user if first_history else None

        return {
            "path": "somepath",
            "method": "GET",
            "content_type": "application/json",
            "data": {},
            "user_pk": created_by.pk
        } if created_by else None

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
                description = f"Can't get total records from remote service by requesting {second_response.request.url} url. \n"
                description += f"http status code: {second_response.status_code}\n"
                description += f"response:\n{second_response.text}"
                BackgroundProcessLog.objects.create(
                    background_process=self.background_process,
                    log_type=LogTypeEnum.ERROR.value,
                    description=description
                )

        self.save()
        return self.total_records

    def _log_response_error(self, response):
        description = f"Something went wrong by requesting {response.request.url} url. \n"
        description += f"http status code: {response.status_code}\n"
        description += f"response:\n{response.text}"
        datestamp = now()
        log = BackgroundProcessLog(
            background_process=self.background_process,
            log_type=LogTypeEnum.ERROR.value,
            description=description,
            date=datestamp
        )
        log.extented_description.save(
            name=f"{datestamp}",
            content=ContentFile(content=response.content),
            save=True)

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
            BackgroundProcessLog.objects.create(
                background_process=self.background_process,
                log_type=LogTypeEnum.WARNING.value,
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
                    "This means if the GetRecords response contains 50 records for example, the request duration was 50 * self.download_duration"))

    objects: TemporaryMdMetadataFileManager = TemporaryMdMetadataFileManager()

    def save(self, *args, **kwargs) -> None:
        from registry.tasks.harvest import \
            call_md_metadata_file_to_db  # to avoid circular import errors
        adding = self._state.adding or self.re_schedule
        self.re_schedule = False

        ret = super().save(*args, **kwargs)

        if adding:
            transaction.on_commit(
                lambda: call_md_metadata_file_to_db.delay(
                    md_metadata_file_id=self.pk,
                    harvesting_job_id=self.job.pk,  # to provide the job id for TaskResult db objects
                    http_request=self.job._http_request(),
                    background_process_pk=self.job.background_process_id if self.job.background_process_id else None
                ))
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
                    'origin': MetadataOriginEnum.CATALOGUE.value if self.job_id else MetadataOriginEnum.FILE_SYSTEM_IMPORT.value,
                    'origin_url': self.job.service.client.get_record_by_id_request(id=md_metadata.file_identifier).url if self.job_id else "http://localhost"
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
                        f"file is neither server nor dataset record. HierarchyLevel: {md_metadata._hierarchy_level}")
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

                            self.import_error = str(import_error)
                            self.save()
                            return db_metadata, update, exists

                    self.delete()

                    return db_metadata, update, exists
            except Exception as e:
                import traceback
                exc_info = sys.exc_info()
                self.import_error = ''.join(
                    traceback.format_exception(*exc_info))
                self.save()
                raise e

    def update_relations(self, md_metadata, exists, update, db_metadata, duration):
        # TODO: is this relation still needed? Or is it enough to collect the harvested through by the harvested_metadata_relations?
        db_metadata.harvested_through.add(self.job.service)

        collecting_state = CollectingStatenEnum.UPDATED if exists and update else CollectingStatenEnum.EXISTING if exists and not update else CollectingStatenEnum.NEW
        return self.job.add_harvested_metadata_relation(
            md_metadata,
            db_metadata,
            collecting_state,
            self.download_duration,
            duration)
