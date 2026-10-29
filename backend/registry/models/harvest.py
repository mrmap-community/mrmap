import json
import sys
from uuid import uuid4

from celery import chord, current_task
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.db import models
from django.contrib.postgres.fields import ArrayField
from django.core.files.base import ContentFile
from django.core.validators import MinValueValidator
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import UniqueConstraint
from django.db.models.fields.files import FieldFile
from django.db.models.query_utils import Q
from django.utils import timezone
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_celery_beat.models import PeriodicTask
from extras.models import AdditionalTimeFieldsHistoricalModel
from lxml import etree
from lxml.etree import XML, XMLParser
from MrMap.celery import app
from notify.enums import ProcessNameEnum, ProcessStatusEnum
from registry.enums.harvesting import (CollectingStatenEnum,
                                       HarvestingPhaseEnum, LogKindEnum,
                                       LogLevelEnum)
from registry.enums.metadata import MetadataOriginEnum
from registry.exceptions.harvesting import InternalServerError
from registry.managers.havesting import (HarvestedMetadataRelationQuerySet,
                                         HarvestingJobManager,
                                         TemporaryMdMetadataFileManager)
from registry.mappers.factory import MDMetadataXmlMapper
from registry.mappers.persistence.handler import PersistenceHandler
from registry.mappers.utils import make_instance_key
from registry.models.metadata import (DatasetMetadataRecord,
                                      ServiceMetadataRecord)
from registry.models.service import CatalogueService
from registry.ows_lib.xml.consts import NAMESPACE_LOOKUP
from registry.settings import (HARVESTING_REQUEST_TIMEOUT_BASE_SECONDS,
                               HARVESTING_REQUEST_TIMEOUT_MAX_SECONDS,
                               HARVESTING_REQUEST_TIMEOUT_PER_RECORD_SECONDS,
                               MIN_STEP_SIZE)
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
        # Do not use this setting.
        # From django docs: Automatically set the field to now when the object is first created.
        # Useful for creation of timestamps. Note that the current date is always used;
        # it’s not just a default value that you can override.
        # So even if you set a value for this field when creating the object, it will be ignored.
        # If you want to be able to modify this field, set the following instead of auto_now_add=True:
        # auto_now_add=True,
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
        current_task_id = current_task.request.id if current_task else None
        task_ids = [str(_id) for _id in self.celery_task_ids
                    if str(_id) != current_task_id]
        if task_ids:
            # A failing task can abort its own harvest. Store the terminal state and
            # log before terminating siblings, and let the current task finish.
            transaction.on_commit(lambda: app.control.revoke(task_ids, terminate=True))
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
        with transaction.atomic():
            current = self._meta.model.objects.select_for_update().get(pk=self.pk)
            self.celery_task_ids = current.celery_task_ids + ids
            self._meta.model.objects.filter(pk=self.pk).update(
                celery_task_ids=self.celery_task_ids)


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
    download_duration = models.DurationField(null=True,
                                             blank=True,
                                             verbose_name=_(
                                                 "download duration"),
                                             help_text=_("This is the duration it tooked proportionately to download this record. "
                                                         "This means if the GetRecords response contains 50 records for example, the request duration was 50 * self.download_duration"
                                                         "To get the download duration over all for one harvesting job, aggregate this col."))
    processing_duration = models.DurationField(null=True,
                                               blank=True,
                                               verbose_name=_(
                                                   "processing duration"),
                                               help_text=_("This is the duration it tooked to handle the processing of creating or updating this record."))
    history_date = models.DateTimeField(auto_now_add=True,
                                        verbose_name=_('Created DateTime'),
                                        help_text=_(
                                            'Datetime field when the relation was created'),
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
                condition=(Q(dataset_metadata_record__isnull=True)
                           ^ Q(service_metadata_record__isnull=True)),
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
            "the step size this job asks the catalogue with by a single "
            "GetRecords request. A job which is started without one takes the "
            "step size the catalogue is known to answer."),
        default=50,
        validators=[MinValueValidator(MIN_STEP_SIZE)])
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
    background_process = models.ForeignKey(
        to="notify.BackgroundProcess",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="harvesting_job_processes",
        related_query_name="harvesting_job_process",
        verbose_name=_('background process'),
        help_text=_('the background process which reports this job'))
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
        if related_object.__class__.__name__ == "DatasetMetadataRecord":
            kwargs.pop("service_metadata_record")
            kwargs.update({"dataset_metadata_record": related_object})
        try:
            with transaction.atomic():
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

    def handle_total_records_defined(self, recovering=False):
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
                    recovering=recovering,
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

            # the harvest runs from now on: the process of the job tells the
            # overview of the background activity what the job is doing
            self.report_process(
                ProcessStatusEnum.RUNNING,
                phase=str(HarvestingPhaseEnum.DOWNLOAD_RECORDS.label),
                total_steps=round_trips + self.total_records + 1)

            # publishing tasks on commit was successfully
            transaction.on_commit(
                lambda: chord(
                    tasks,
                    callback
                ).apply_async(
                    max_retries=300,
                    interval=1)
            )

        self.log(
            description=f"phase {HarvestingPhaseEnum.DOWNLOAD_RECORDS.value} started. {round_trips} round trips with step size {self.max_step_size} are needed."
        )

    # TODO: implement three phases:
    # 1. fetch total_records
    # 2. get statistic information about the average response duration with different step sizes
    # 3. start harvesting with the best average response duration step settings

    def build_process(self):
        """Build the process which reports this job in the background activity.

        A harvest is long running work which is done by workers without a
        request to attach a process to, so the job creates its process while it
        is created and the tasks of the job keep it up to date until the job
        decided about itself.

        Returns:
            BackgroundProcess: a process naming the catalogue which is harvested
        """
        # imported here, because the process only reports this job and is not a
        # part of its result
        from notify.models import BackgroundProcess

        service = self.service if getattr(self, 'service_id', None) else None
        title = getattr(service, 'title', None)
        return BackgroundProcess.objects.create(
            phase="Background process created",
            process_type=ProcessNameEnum.HARVESTING.value,
            description=f"Harvesting of the catalogue {title}"[:512] if title
            else str(self._meta.verbose_name),
            related_resource_type=ContentType.objects.get_for_model(service)
            if service else None,
            related_id=service.pk if service else None)

    def report_process(self, status, phase=None, total_steps=None):
        """Mirror the state of this job in the process which reports it.

        Args:
            status (ProcessStatusEnum): the status to report
            phase (str): current phase of the harvest, optional
            total_steps (int): amount of steps the harvest is made of, optional

        Returns:
            int: amount of processes which were updated
        """
        from notify.models import BackgroundProcess

        return BackgroundProcess.objects.report(
            self.background_process_id, status, phase=phase,
            total_steps=total_steps)

    def fail_process(self, error):
        """Report that a task of this job gave up.

        A page which keeps failing never completes the harvest, so without this
        report the harvest would stay as running in the overview of the
        background activity although it ended.
        """
        from notify.models import BackgroundProcess

        BackgroundProcess.objects.log(
            self.background_process_id, f"An error occurred: {error}")
        return self.report_process(
            ProcessStatusEnum.FAILED,
            phase=f"An error occurred: {str(error)[:400]}")

    def save(self, skip_history_when_saving=True, *args, **kwargs):
        if self._state.adding and self.background_process_id is None:
            self.background_process = self.build_process()
        if self._state.adding and self.service:
            return self.handle_adding(*args, **kwargs)
        elif self.total_records == 0:
            # error case. CSW does not provide records for our default request behaviour.
            self.done_at = now()
            self.phase = HarvestingPhaseEnum.COMPLETED.value
            saved = super(HarvestingJob, self).save(*args, **kwargs)
            self.report_process(
                ProcessStatusEnum.COMPLETED,
                phase=str(HarvestingPhaseEnum.COMPLETED.label))
            return saved
        elif self.phase == HarvestingPhaseEnum.ABORT.value:
            with transaction.atomic():
                self.abort()
                saved = super(HarvestingJob, self).save(*args, **kwargs)
                self.report_process(
                    ProcessStatusEnum.ABORTED,
                    phase=str(HarvestingPhaseEnum.ABORTED.label))
                return saved

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

    def get_total_records(self, response):
        ns = {
            "csw": NAMESPACE_LOOKUP["csw_2_0_2"]
        }
        tree = etree.fromstring(response.content)
        search_results = tree.find(
            ".//csw:SearchResults",
            namespaces=ns
        )
        total_records = int(search_results.get("numberOfRecordsMatched", 0))
        return total_records

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

        self.total_records = self.get_total_records(first_response)
        if not self.total_records:
            # try again, cause some csw server implementations are broken and don't support our default TypeName query param
            second_response: Response = client.send_request(
                request=client.get_records_request(
                    type_names="csw:Record",
                    xml_constraint=client.get_constraint(record_types=self.get_record_types())),
                timeout=60)

            # the fallback is the response to judge: the first response was fine, it only named no
            # records at all (#689)
            if self._check_xml_response(second_response):
                self._log_response_error(response=second_response)
                self.total_records = 0
                self.save()
                return self.total_records

            self.total_records = self.get_total_records(second_response)

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

        if self.total_records:
            # the size the fan-out is planned with is what the catalogue answers, not a default
            # nobody chose (#694); the probe shrinks max_step_size before this save, so the run
            # is planned and remembered with the size the service is known to answer
            self.probe_max_step_size()

        self.save()
        return self.total_records

    def get_request_timeout(self, max_records: int) -> int:
        """How long one GetRecords request for a page of this size may take (#694).

        The time scales with the requested size: a catalogue which answers a big page slowly
        must not be answered with a timeout, because that would read as a size which does not
        work and shrink the harvest towards smaller pages for no reason.
        """
        return int(min(
            HARVESTING_REQUEST_TIMEOUT_MAX_SECONDS,
            HARVESTING_REQUEST_TIMEOUT_BASE_SECONDS
            + max_records * HARVESTING_REQUEST_TIMEOUT_PER_RECORD_SECONDS))

    def probe_max_step_size(self) -> int:
        """Ask the catalogue which page size it answers, before the fan-out is planned (#694).

        One GetRecords request with resultType=hits asks about a size without asking for
        records; a catalogue which cannot answer that many records per request refuses such a
        request the same way it refuses the real ones. Halving down to MIN_STEP_SIZE finds the
        biggest size the service answers, and that size is what handle_total_records_defined
        plans the fan-out with - and what complete_harvest keeps on the catalogue as the size
        this service is known to answer. The size the run starts from is never exceeded, the
        probe only ever shrinks it. A server error is no answer about a size: it raises like
        anywhere else on the request path and gets retried or ends the job as #690 defines.
        """
        client = self.service.client
        planned = self.max_step_size
        hint = client.advertised_max_records()
        size = min(planned, hint) if hint else planned
        while True:
            response: Response = client.send_request(
                request=client.get_records_request(
                    result_type="hits",
                    max_records=size,
                    start_position=1,
                    xml_constraint=client.get_constraint(
                        record_types=self.get_record_types())),
                timeout=self.get_request_timeout(size))
            if not self._check_xml_response(response):
                break
            if size <= MIN_STEP_SIZE:
                # even the smallest size is refused; the run stays at it and every page of it
                # leaves the trace of missing records which #690 defines
                break
            halved = max(size // 2, MIN_STEP_SIZE)
            self.log(
                level=LogLevelEnum.WARNING.value,
                description=f"catalogue refused GetRecords with maxRecords={size}, probing {halved}")
            size = halved
        if size != planned:
            self.max_step_size = size
            self.log(
                description=f"catalogue answers GetRecords with maxRecords={size}; the harvest is planned with that size")
        return self.max_step_size

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

    def log_missing_records(self, request, start_position, received):
        """Name the records a page of this run did not deliver.

        A page which came back short and a page which the catalogue refused both leave a snapshot
        behind which is shorter than the run planned. The log of it is what makes such a run visibly
        incomplete: the harvest history keeps it out of the complete snapshots and the harvest alert
        of the catalogue answers it (#690).
        """
        should_return_count = self.max_step_size if start_position + \
            self.max_step_size < self.total_records else self.total_records - start_position

        if received >= should_return_count:
            return
        self.log(
            level=LogLevelEnum.WARNING.value,
            kind=LogKindEnum.COUNT_MISSMATCH.value,
            description=f"{received}<{should_return_count}",
            extented_description=f"Only {received} received from {should_return_count} possible records.\n" +
            f"URL: {request.url}"
        )

    def _check_xml_is_parseable(self, xml: str) -> bool:
        try:
            XML(xml, XMLParser())
        except Exception:
            return False
        return True

    def _check_xml_response(self, response):
        if not response.ok or not self._check_xml_is_parseable(response.content) or "<ExceptionReport" in response.text:
            self._log_response_error(response=response)
            # only the server error class is worth another request; a chained comparison like
            # ">= 500 <= 600" asks "500 <= 600" and would retry everything from 500 upwards (#689)
            if 500 <= response.status_code < 600:
                raise InternalServerError
            return True
        return False

    def get_stored_page_count(self, request) -> int:
        """how many records this job already stores for exactly this request; the requested url
        carries maxRecords and startPosition, so it is the identity of a page"""
        return TemporaryMdMetadataFile.objects.filter(
            job=self, requested_url=request.url).count()

    def fetch_records(self, start_position, check_existing=True) -> int:
        """Download the records of one planned page.

        The page is asked for with the step size this job plans with. A catalogue which refuses
        exactly that size is not answered with the loss of the whole page: the still missing part
        of the page's range is asked again with a halved size, down to MIN_STEP_SIZE - bounded
        and inside this one task, so the chord of the run stays flat (#694). A page which stays
        without records even at the smallest size is answered the way #690 defines it: the log
        names the records this run did not deliver.
        """
        client = self.service.client
        request = client.get_records_request(
            max_records=self.max_step_size,
            start_position=start_position,
            result_type="results",
            xml_constraint=client.get_constraint(
                record_types=self.get_record_types())
        )

        # a page whose records are already stored is complete, so nothing is asked of the remote
        # service for it again: every scheduled tick which fires while a harvest is running
        # redelivers the whole fan-out and would otherwise download every page a second time
        # (#688). The transactional check inside _store_page stays in place, because the row
        # count read under the job lock is what guards two workers storing the same page at the
        # same time.
        if check_existing:
            existing_count = self.get_stored_page_count(request)
            if existing_count:
                return existing_count

        received = self._fetch_range(
            client=client,
            start_position=start_position,
            size=self.max_step_size,
            check_existing=check_existing)

        if received is None:
            # the job was completed or aborted while this page was downloading
            return 0

        self.log_missing_records(
            request=request, start_position=start_position, received=received)
        return received

    def _fetch_range(self, client, start_position, size, check_existing):
        """Fetch the records of the range [start_position, start_position + size) and answer how
        many arrived; None if the job closed while the range was downloading.

        The whole range is asked for with `size` first, and a catalogue which answers that
        request - even with fewer records than asked for - ends the page with one request like
        before: fewer records than promised is the answer of the end of a catalogue as much as of
        a silent cap, and only the trace of #690 tells the two apart, so re-asking smaller sizes
        on every short page would multiply the requests to the remote service for a guess. Only
        a request which comes back without any record - the usual answer to a maxRecords the
        catalogue refuses - makes the missing part of the range ask again with a halved size.
        Once the range is on a smaller size which answers, its rest is harvested at that size;
        a page grows back to the planned size only with the next run, where the probe of #694
        measures it against the catalogue again.
        """
        position = start_position
        remaining = size
        step_size = size
        received = 0
        while remaining > 0:
            request = client.get_records_request(
                max_records=step_size,
                start_position=position,
                result_type="results",
                xml_constraint=client.get_constraint(
                    record_types=self.get_record_types())
            )
            if check_existing:
                stored = self.get_stored_page_count(request)
                if stored:
                    received += stored
                    position += stored
                    remaining -= stored
                    if step_size == size:
                        break
                    continue
            response: Response = client.send_request(
                request=request,
                timeout=self.get_request_timeout(step_size))
            refused = self._check_xml_response(response)
            stored = 0 if refused else self._store_page(
                response, request, start_position=position)
            if stored is None:
                return None
            if stored:
                received += stored
                position += stored
                remaining -= stored
                if step_size == size:
                    # the catalogue answered the planned size; the page is done with its answer,
                    # a possible shortage is the trace of #690
                    break
                continue
            if received and self.total_records is not None and position > self.total_records:
                # this range reaches beyond the records the catalogue counted for this run; what
                # is missing is answered by log_missing_records, not by more requests
                break
            if step_size <= MIN_STEP_SIZE:
                break
            halved = max(step_size // 2, MIN_STEP_SIZE)
            self.log(
                level=LogLevelEnum.WARNING.value,
                description=(
                    f"GetRecords with maxRecords={step_size} at startPosition {position} "
                    f"{'was refused' if refused else 'came back without records'}, "
                    f"the missing part is asked with {halved}"))
            step_size = halved
        return received

    def _store_page(self, response, request, start_position):
        """Store the records of one answered GetRecords response.

        Answers None when the job is not open for downloading anymore, and the number of stored
        records otherwise - which is the count another worker stored when it won the race for
        exactly this request under the job lock (#688).
        """
        tree = etree.fromstring(response.content)

        # Namespaces definieren
        ns = {
            "gmd": "http://www.isotc211.org/2005/gmd"  # NOSONAR normative ISO 19139 gmd namespace identifier, used as an lxml xpath prefix - not a network endpoint
        }

        # Alle MD_Metadata-Elemente finden
        md_elements = tree.xpath("//gmd:MD_Metadata", namespaces=ns)
        datestamp = timezone.now()

        with transaction.atomic():
            job = HarvestingJob.objects.select_for_update().get(pk=self.pk)
            if job.done_at is not None or job.phase > HarvestingPhaseEnum.DOWNLOAD_RECORDS:
                return None
            existing_count = self.get_stored_page_count(request)
            if existing_count:
                return existing_count
            db_md_metadata_file_list = []
            records_count = len(md_elements)

            for idx, md_metadata in enumerate(md_elements, start=1):
                db_md_metadata_file: TemporaryMdMetadataFile = TemporaryMdMetadataFile(
                    job=self,
                    request_id=datestamp,
                    requested_url=request.url,
                    download_duration=response.elapsed / records_count
                )

                # save the file without saving the instance in db... this will be done with bulk_create
                xml_bytes = etree.tostring(
                    md_metadata,
                    xml_declaration=True,
                    encoding="UTF-8",
                    pretty_print=True
                )

                db_md_metadata_file.md_metadata_file.save(
                    name=f"record_nr_{idx + start_position}",
                    content=ContentFile(content=xml_bytes),
                    save=False)
                db_md_metadata_file_list.append(db_md_metadata_file)

            db_objs = TemporaryMdMetadataFile.objects.bulk_create(
                objs=db_md_metadata_file_list,
                ignore_conflicts=True,
                batch_size=50
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
        if self.re_schedule:
            self.has_import_error = False
            self.import_error = ""
        self.re_schedule = False

        ret = super().save(*args, **kwargs)

        if adding:
            task_id = uuid4()

            task = call_md_metadata_file_to_db.s(
                md_metadata_file_id=self.pk,
                harvesting_job_id=self.job.pk,  # to provide the job id for TaskResult db objects
                http_request=self.job._http_request(),
            )
            task.set(task_id=str(task_id))

            self.job.append_celery_task_ids([task_id])

            transaction.on_commit(lambda: task.apply_async())
        return ret

    def delete(self, *args, **kwargs):
        storage = self.md_metadata_file.storage
        name = self.md_metadata_file.name
        ret = super().delete(*args, **kwargs)
        if name:
            transaction.on_commit(lambda: storage.delete(name))
        return ret

    def md_metadata_file_to_db(self):
        with self.md_metadata_file.open('rb') as _file:
            try:
                with transaction.atomic():
                    start_db_processing = now()

                    mappers = MDMetadataXmlMapper.from_xml(_file.read())
                    instances = mappers[0].xml_to_django()
                    result = []
                    for instance in instances:
                        handler = PersistenceHandler(
                            mapper=mappers[0],
                            defaults={
                                "dataset": {
                                    "origin": MetadataOriginEnum.CATALOGUE.value if self.job.service_id else MetadataOriginEnum.FILE_SYSTEM_IMPORT.value,
                                    'origin_url': self.job.service.client.get_record_by_id_request(id=instance.file_identifier).url if self.job.service_id else "http://localhost"
                                },
                                "service": {
                                    "origin": MetadataOriginEnum.CATALOGUE.value if self.job.service_id else MetadataOriginEnum.FILE_SYSTEM_IMPORT.value,
                                    'origin_url': self.job.service.client.get_record_by_id_request(id=instance.file_identifier).url if self.job.service_id else "http://localhost"
                                }
                            }
                        )
                        created_instances = handler.persist_all()
                        key = make_instance_key(instance)

                        created_instance = created_instances.get(
                            instance.__class__, {}).get(key, None)
                        # after persit handler has created the instances on db side, the objects are no longer identical

                        if created_instance:
                            created, update = created_instance._custom_state
                            if self.job:
                                end_db_processing = now()
                                relation = self.update_relations(
                                    not created,
                                    update,
                                    created_instance,
                                    end_db_processing - start_db_processing
                                )
                                if relation.collecting_state == CollectingStatenEnum.DUPLICATED.value:
                                    # do not delete this entries for analyze purposes
                                    import_error = {
                                        "reason": "duplicated",
                                        "db_metadata.pk": created_instance.pk,
                                        "db_metadata.file_identifier": created_instance.file_identifier,
                                        "db_metadata.code_space": created_instance.code_space,
                                        "db_metadata.code": created_instance.code,
                                    }
                                    self.has_import_error = True
                                    self.import_error = str(import_error)
                                    self.save()
                                    return created_instance, update, not created
                                elif update or created:
                                    # something has changed... so tell us from what service this changes come from
                                    update_change_reason(
                                        created_instance,
                                        'fileimport'if self.job.service is None else f'csw:{self.job.service}'
                                    )
                            result.append(
                                (created_instance, update, not created))
                            if self.job:
                                for warning in mappers[0].warnings:
                                    self.job.log(
                                        level=LogLevelEnum.WARNING.value,
                                        description=warning[:512],
                                        extented_description=(
                                            f"Metadata record: {instance.file_identifier}\n"
                                            f"Source file: {self.md_metadata_file.name}\n"
                                            f"{warning}\n"
                                            "The remaining metadata was imported."
                                        ),
                                    )
                            self.delete()
                    return result
            except OperationalError:
                raise
            except Exception as e:
                import traceback
                exc_info = sys.exc_info()
                self.import_error = ''.join(
                    traceback.format_exception(*exc_info))
                self.has_import_error = True
                self.save()
                raise e

    def update_relations(self, exists, update, db_metadata, duration):
        # TODO: is this relation still needed?
        # Or is it enough to collect the harvested through by the harvested_metadata_relations?
        if self.job.service:
            db_metadata.harvested_through.add(self.job.service)

        collecting_state = CollectingStatenEnum.UPDATED.value if exists and update else CollectingStatenEnum.EXISTING.value if exists and not update else CollectingStatenEnum.NEW.value
        return self.job.add_harvested_metadata_relation(
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
        # Do not use this setting.
        # From django docs: Automatically set the field to now when the object is first created.
        # Useful for creation of timestamps. Note that the current date is always used;
        # it’s not just a default value that you can override.
        # So even if you set a value for this field when creating the object, it will be ignored.
        # If you want to be able to modify this field, set the following instead of auto_now_add=True:
        # auto_now_add=True,
        default=now,
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
        if not self.pk:
            if not self.task:
                self.task = "registry.tasks.harvest.create_harvesting_job"
            if not self.queue:
                self.queue = "default"
            if not self.name:
                self.name = str(uuid4())
            if not self.kwargs or self.kwargs == '{}':
                system_user, _ = get_user_model().objects.get_or_create(username="system")
                http_request = {
                    "path": "/periodic-harvesting-job",
                    "method": "GET",
                    "content_type": "application/json",
                    "data": {},
                    "user_pk": str(system_user.pk)
                }
                self.kwargs = json.dumps({
                    "service_id": str(self.service.pk),
                    "http_request": http_request,
                })

    class Meta:
        verbose_name = _('Periodic Harvesting Job')
        verbose_name_plural = _('Periodic Harvesting Jobs')
