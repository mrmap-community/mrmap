from celery import chord
from django.db import models, transaction
from django.db.models import (Case, Count, DateTimeField, ExpressionWrapper, F,
                              FloatField, Func, IntegerField, OuterRef, Q,
                              Subquery, TextField, Value, When)
from django.db.models.functions import (Cast, Ceil, Coalesce, Concat, Greatest,
                                        Round)
from django.utils.timezone import now
from django_cte import CTEManager
from extras.managers import DefaultHistoryManager
from notify.enums import ProcessNameEnum, ProcessStatusEnum
from notify.tasks import finish_background_process
from registry.enums.harvesting import CollectingStatenEnum, HarvestingPhaseEnum
from registry.expressions.durations import DurationSeconds
from registry.querys.havesting import HarvestingJobQuerySet, run_created_at

# The answers about a run which are no column of its row but a number read from
# its work: the steps it took, how far it came, and what it measures while it is
# still working. They are named in the spelling of the api, because that is how a
# client asks for them with a sparse fieldset, and `with_run_progress` answers
# exactly the named ones (see HarvestingJobViewSetMixin.with_unhandled_records).
RUN_PROGRESS_FIELDS = (
    "unhandledRecordsCount", "importErrorCount",
    "totalSteps", "doneSteps", "progress",
    "elapsedSeconds", "recordsPerMinuteRunning",
    "estimatedSecondsRemaining", "expectedDoneAt",
)

# The phases in which a run works: a run which ended or was aborted has nothing
# left to measure and nothing left to estimate (#1071).
CLOSED_PHASES = [HarvestingPhaseEnum.ABORT.value,
                 HarvestingPhaseEnum.ABORTED.value]


class HarvestedMetadataRelationQuerySet(models.QuerySet):
    def stats_per_day(self):
        return self.values(
            "history_day",
            "collecting_state",
            "harvesting_job",
            "harvesting_job__service"
        ).annotate(
            id=F("history_day"),
            new=Count("pk", filter=(
                Q(collecting_state=CollectingStatenEnum.NEW.value))),
            updated=Count("pk", filter=Q(
                collecting_state=CollectingStatenEnum.UPDATED.value)),
            existed=Count("pk", filter=Q(
                collecting_state=CollectingStatenEnum.EXISTING.value)),
            service=F("harvesting_job__service")
        )


class HarvestingJobManager(DefaultHistoryManager, CTEManager):

    def get_queryset(self):
        """The queryset of the aggregate, which can carry a count it has read.

        ``registry/querys/havesting.py``: the statistics of a page of jobs are
        bounded by a CTE over the whole table of the harvested metadata relations,
        and the paginator of the overview asks that annotated queryset for the
        number of rows of the answer (#885).
        """
        return HarvestingJobQuerySet(self.model, using=self._db)

    def with_temporary_file_counts(self, qs=None, **counts):
        """Count only the files of each selected job, including after pagination.

        Interrupted jobs retain their files for recovery. Aggregating all jobs
        before joining their counts makes even a small page read that backlog.
        Correlated subqueries use the existing job index and stay lazy so later
        filters and limits also bound the work (#870).

        A count which only the files carrying some property are asked about is
        answered by exactly those files: the filter of the count becomes the
        range of the subquery which answers it, and a range is what the database
        reads out of an index. A COUNT FILTER in front of the whole range reads
        every file of the job to find the few it counts - the job of the report
        read the entries of all 411,518 files of the job to answer how many of
        them had failed, again on every request which rendered its progress
        (#886). The new index over the job and its error flag answers the failed
        files as their own range.
        A job whose files are all of the other kind leaves a filtered range
        without a single row; the ``Coalesce`` answers it the 0 the FILTER had
        counted.
        """
        from registry.models.harvest import TemporaryMdMetadataFile

        if qs is None:
            qs = self.get_queryset()
        files = TemporaryMdMetadataFile.objects.filter(
            job_id=OuterRef("pk")).order_by().values("job_id")
        subqueries = {}
        for name, count in counts.items():
            where = getattr(getattr(count, "filter", None), "condition", None)
            if isinstance(where, Q):
                # a Q selects files and so is a range: the entries of the rows
                # the count is about and no others. Any other expression is not
                # always something a WHERE can filter against and stays a
                # FILTER; an empty Q narrows nothing here, as its FILTER clause
                # is left out of the statement just as well.
                files_of_count = files.filter(where)
                count = count.copy()
                count.filter = None
            else:
                files_of_count = files
            subqueries[name] = Coalesce(Subquery(
                files_of_count.annotate(**{name: count}).values(name)), 0)
        return qs.annotate(**subqueries)

    def with_string_representation(self):
        """Annotate the display string which the serializer answers for a job.

        ``HarvestingJob.__str__`` answers ``<catalogue title> (harvesting job
        <pk>)`` and, for a file import without a catalogue, just ``harvesting
        job <pk>``; the annotation mirrors both branches, so the list orders
        the rows the way its client renders them (#1035, #1045).
        """
        return self.get_queryset().annotate(
            string_representation=Case(
                When(
                    service__isnull=False,
                    then=Concat(
                        "service__title",
                        Value(" (harvesting job "),
                        Cast("pk", TextField()),
                        Value(")"),
                        output_field=TextField())),
                default=Concat(
                    Value("harvesting job "),
                    Cast("pk", TextField()),
                    output_field=TextField()),
                output_field=TextField()))

    def with_run_progress(self, qs=None, answer=RUN_PROGRESS_FIELDS):
        """Answer the steps, the progress and the measurements of a run.

        total_steps, done_steps, progress and the measurements of a run are no
        model fields but annotations, so an instance which was not selected
        through this method has no progress to tell. The websocket payload of a
        HarvestingJob is rendered by the same serializer as the API endpoint -
        fields without a value are simply left out of it, so senders that
        announce a job have to select it here first. The same is done for
        background processes with BackgroundProcess.objects.process_info().

        The annotations derive the steps of the running phase from the temporary
        md metadata files that are still waiting to be imported: while records are
        downloaded their count grows, while they are written to the database it
        shrinks. Every number is read from the row of the job, from the count of
        its own files (``with_temporary_file_counts``, #870, #886) and from its
        change log: the screen which shows these numbers asks them again every few
        seconds while the import of this very run is writing, so nothing here
        aggregates the harvested metadata relations of a run (#1071).

        Args:
            qs: the queryset of harvesting jobs to answer on; the queryset of the
                manager by default
            answer: which of the answers of a run the caller answers, named in
                ``RUN_PROGRESS_FIELDS``. An answer pulls in what it is built from:
                the progress pulls the steps, and an estimate is answered with the
                elapsed time it scales and with the end it names.
        """
        want = set(answer)
        estimating = bool(
            want & {"estimatedSecondsRemaining", "expectedDoneAt"})
        measuring = bool(want & {
            "elapsedSeconds", "recordsPerMinuteRunning",
            "estimatedSecondsRemaining", "expectedDoneAt"})
        done_steps_asked = estimating or bool(want & {"doneSteps", "progress"})
        total_steps_asked = done_steps_asked or "totalSteps" in want
        # the total steps are derived from the row alone; only the done steps and
        # the stored records are read from the files of the job
        files_counted = done_steps_asked or "recordsPerMinuteRunning" in want

        if qs is None:
            qs = self.get_queryset()

        counts = {}
        if "importErrorCount" in want:
            counts.update({
                "import_error_count": Count("id", filter=Q(has_import_error=True))
            })
        if "unhandledRecordsCount" in want:
            counts.update({
                "unhandled_records_count": Count(
                    "id", filter=Q(has_import_error=False))
            })
        if files_counted:
            counts.update({"records_count": Count("id")})
        if counts:
            qs = self.with_temporary_file_counts(qs, **counts)

        annotations = {}
        if total_steps_asked:
            annotations.update({
                "download_tasks_count": Ceil(
                    F("total_records") / F("max_step_size")),
                # + 1 for call_fetch_total_records
                "total_steps": F("download_tasks_count") + F("total_records") + 1,
            })
        if done_steps_asked:
            annotations.update({
                "done_steps": Case(
                    When(
                        condition=Q(
                            phase__gte=HarvestingPhaseEnum.COMPLETED.value),
                        then=F("total_steps")
                    ),
                    When(
                        condition=Q(
                            phase=HarvestingPhaseEnum.DOWNLOAD_RECORDS.value),
                        then=1 + Ceil(F("records_count") /
                                      F("max_step_size"))
                    ),
                    When(
                        condition=Q(
                            phase=HarvestingPhaseEnum.RECORDS_TO_DB.value),
                        then=1 + F("download_tasks_count") + F("total_records") - F("records_count")
                    ),
                    default=0
                ),
            })
        if "progress" in want:
            annotations.update({
                "progress": Case(
                    When(
                        ~Q(phase=HarvestingPhaseEnum.ABORTED.value) & Q(
                            done_at__isnull=False),
                        then=Value(100.0)
                    ),
                    default=Case(
                        When(
                            total_steps__gt=0,
                            then=Round(
                                F("done_steps") * 1.0 /
                                F("total_steps") * 100.0,
                                precision=2,
                                output_field=FloatField()
                            ),
                        ),
                        default=0.0
                    ),
                    output_field=FloatField()
                )
            })
        if measuring:
            annotations.update(self.run_measurements(want))

        if annotations:
            qs = qs.annotate(**annotations)
        return qs

    @staticmethod
    def run_measurements(want):
        """The annotations which answer how long a run works and how fast it is.

        Which of them are answered is up to the caller (`with_run_progress`);
        `elapsed_seconds` is answered for every one of them, because the others
        are built on it. Nothing here reads the harvested metadata relations: the
        records a run has stored so far come from the count of its own temporary
        files, the part which is left from the steps it already answers, and the
        moment the run was made from its row or its change log (#1071).

        Args:
            want (set): the measurement answers of ``RUN_PROGRESS_FIELDS``

        Returns:
            dict: the annotations by their name, in the order they build on
                each other
        """
        def ends_at():
            """The moment the run stopped working, or this request while it works.

            One moment for all of the numbers: the elapsed time of a run and the
            moment it is expected to end have to answer the same clock.
            """
            return Coalesce(
                F("done_at"),
                Value(now(), output_field=DateTimeField()),
                output_field=DateTimeField())

        def working():
            """Whether the run is still working.

            A run which ended measured a harvest as a whole and is answered by
            `records_per_minute` (#692); a run which was aborted measures the work
            it happened to do, which is no harvest (#1071).
            """
            return Q(done_at__isnull=True) & ~Q(phase__in=CLOSED_PHASES)

        def stored():
            """The records the run has stored so far, while it works.

            While the run downloads, the records it stored are the files it put on
            its own backlog; while it imports, the files still waiting are the
            ones which are NOT stored yet, because an imported file is gone (see
            `registry.tasks.harvest.import_md_metadata_file`). A run whose records
            are not known yet has nothing stored to answer.
            """
            return Case(
                When(Q(total_records__isnull=True), then=None),
                When(Q(phase=HarvestingPhaseEnum.RECORDS_TO_DB.value),
                     then=Greatest(F("total_records") - F("records_count"), 0)),
                default=F("records_count"),
                output_field=IntegerField())

        annotations = {"elapsed_seconds": ExpressionWrapper(
            DurationSeconds(ends_at()) - DurationSeconds(run_created_at()),
            output_field=FloatField())}
        if "recordsPerMinuteRunning" in want:
            annotations.update({
                "records_per_minute_running": Case(
                    When(working() & Q(elapsed_seconds__gt=0),
                         then=ExpressionWrapper(
                             stored() * 60.0 / F("elapsed_seconds"),
                             output_field=FloatField())),
                    default=None,
                    output_field=FloatField())
            })
        if want & {"estimatedSecondsRemaining", "expectedDoneAt"}:
            annotations.update({
                "estimated_seconds_remaining": Case(
                    # What a run has left is the part of its steps which is not
                    # done, scaled by the time the done part measured. A run whose
                    # records are not known yet, whose progress is nothing, or
                    # which is closed answers no remaining time - following
                    # `harvest_durations`, which answers no row for a catalogue
                    # which never finished a harvest, so that an invented estimate
                    # cannot be mistaken for a measured one (#693, #1071).
                    When(working() & Q(total_records__isnull=False)
                         & Q(done_steps__gt=0) & Q(elapsed_seconds__gt=0),
                         then=ExpressionWrapper(
                             F("elapsed_seconds")
                             * Greatest(F("total_steps") - F("done_steps"), 0)
                             * 1.0 / F("done_steps"),
                             output_field=FloatField())),
                    default=None,
                    output_field=FloatField())
            })
        if "expectedDoneAt" in want:
            annotations.update({
                "expected_done_at": Func(
                    ExpressionWrapper(
                        DurationSeconds(ends_at())
                        + F("estimated_seconds_remaining"),
                        output_field=FloatField()),
                    function="TO_TIMESTAMP",
                    output_field=DateTimeField())
            })
        return annotations

    def with_process_info(self):
        """Adds the progress information of a harvesting job to the queryset.

        The payload of a push is rendered by the serializer of the api, which
        answers every field it finds on the instance, so this has to be the whole
        set of what a screen of a run shows: a field which only the endpoint
        annotated would answer once and empty with the first push.
        """
        return self.with_run_progress(answer=RUN_PROGRESS_FIELDS)


class TemporaryMdMetadataFileManager(models.Manager):

    def bulk_create_with_task_scheduling(self, objs, *args, **kwargs):
        from notify.models import BackgroundProcess
        from registry.models.harvest import HarvestingJob
        # to avoid circular import errors
        from registry.tasks.harvest import (call_md_metadata_files_to_db,
                                            iter_md_metadata_file_chunks)

        bp = BackgroundProcess.objects.create(
            total_steps=len(objs) + 1,
            phase=HarvestingPhaseEnum.RECORDS_TO_DB.value,
            # the overview of the background activity names every process by its
            # type and what it does, so a harvesting process has to tell both
            process_type=ProcessNameEnum.HARVESTING.value,
            description=f"Harvesting of {len(objs)} metadata files")
        hj = HarvestingJob.objects.create(
            total_records=len(objs),
            # the process built above reports exactly the work of this job, so
            # the job keeps it instead of building a second one
            background_process=bp)
        for obj in objs:
            obj.job = hj

        super().bulk_create(objs=objs, *args, **kwargs)

        db_objs = self.get_queryset().filter(job__id=objs[0].job_id)
        request = db_objs[0].job._http_request()

        # one task per chunk of files instead of one per file, so a directory with
        # thousands of files does not publish thousands of broker messages (#859)
        to_db_tasks = [
            call_md_metadata_files_to_db.s(
                md_metadata_file_ids=chunk,
                http_request=request,
                background_process_pk=bp.pk)
            for chunk in iter_md_metadata_file_chunks(obj.id for obj in db_objs)
        ]
        if to_db_tasks:
            transaction.on_commit(
                lambda: chord(to_db_tasks).apply_async(
                    finish_background_process.s(
                        http_request=request,
                        background_process_pk=bp.pk,
                    ),
                    max_retries=300,
                    interval=1
                )
            )
        else:
            BackgroundProcess.objects.filter(pk=bp.pk).update(
                phase=HarvestingPhaseEnum.COMPLETED.value,
                status=ProcessStatusEnum.COMPLETED,
                done_at=now(),
                done_steps=F('total_steps')
            )

        return db_objs
