from celery import chord
from django.db import models, transaction
from django.db.models import (Case, Count, F, FloatField, OuterRef, Q,
                              Subquery, Value, When)
from django.db.models.functions import Ceil, Coalesce, Round
from django.utils.timezone import now
from django_cte import CTEManager
from extras.managers import DefaultHistoryManager
from notify.enums import ProcessNameEnum, ProcessStatusEnum
from notify.tasks import finish_background_process
from registry.enums.harvesting import CollectingStatenEnum, HarvestingPhaseEnum
from registry.querys.havesting import HarvestingJobQuerySet


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

    def with_process_info(self):
        """Adds the progress information of a harvesting job to the queryset.

        total_steps, done_steps, progress and the two record counters are no
        model fields but annotations, so an instance which was not selected
        through this method has no progress to tell. The websocket payload of a
        HarvestingJob is rendered by the same serializer as the API endpoint -
        fields without a value are simply left out of it, so senders that
        announce a job have to select it here first. The same is done for
        background processes with BackgroundProcess.objects.process_info().

        The annotations are the ones of HarvestingJobViewSet
        (with_unhandled_records), which derives the steps of the running phase
        from the temporary md metadata files that are still waiting to be
        imported: while records are downloaded their count grows, while they
        are written to the database it shrinks.
        """
        qs = self.with_temporary_file_counts(
            unhandled_records_count=Count(
                "id", filter=Q(has_import_error=False)),
            import_error_count=Count(
                "id", filter=Q(has_import_error=True)),
            records_count=Count("id"),
        ).annotate(
            download_tasks_count=Ceil(
                F("total_records") / F("max_step_size"))
        ).annotate(
            # + 1 for call_fetch_total_records
            total_steps=F("download_tasks_count") + F("total_records") + 1
        ).annotate(
            done_steps=Case(
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
            )
        ).annotate(
            progress=Case(
                When(
                    ~Q(phase=HarvestingPhaseEnum.ABORTED.value) & Q(
                        done_at__isnull=False),
                    then=Value(100.0)
                ),
                default=Case(
                    When(
                        total_steps__gt=0,
                        then=Round(F("done_steps") * 1.0 / F("total_steps") * 100.0, precision=2),  # noqa

                    ),
                    default=0.0
                ),
                output_field=FloatField()
            )
        )

        return qs


class TemporaryMdMetadataFileManager(models.Manager):

    def bulk_create_with_task_scheduling(self, objs, *args, **kwargs):
        from notify.models import BackgroundProcess
        from registry.models.harvest import HarvestingJob
        from registry.tasks.harvest import \
            call_md_metadata_file_to_db  # to avoid circular import errors

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

        to_db_tasks = [
            call_md_metadata_file_to_db.s(
                md_metadata_file_id=obj.id,
                http_request=request,
                background_process_pk=bp.pk)
            for obj in db_objs
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
