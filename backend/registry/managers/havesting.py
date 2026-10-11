from celery import chord
from django.db import models, transaction
from django.db.models import Case, Count, F, FloatField, Q, Value, When
from django.db.models.functions import Ceil, Round
from django.utils.timezone import now
from django_cte import CTEManager
from extras.managers import DefaultHistoryManager
from notify.enums import ProcessStatusEnum
from notify.tasks import finish_background_process
from registry.enums.harvesting import CollectingStatenEnum, HarvestingPhaseEnum


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


class HarvestedMetadataRelationManager(models.Manager.from_queryset(HarvestedMetadataRelationQuerySet)):
    pass


class HarvestingJobManager(DefaultHistoryManager, CTEManager):

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
        qs = self.get_queryset()

        qs = qs.annotate(
            unhandled_records_count=Count(
                "temporary_md_metadata_file",
                filter=Q(temporary_md_metadata_file__has_import_error=False)),
            import_error_count=Count(
                "temporary_md_metadata_file",
                filter=Q(temporary_md_metadata_file__has_import_error=True)),
            records_count=Count("temporary_md_metadata_file"),
            download_tasks_count=Ceil(
                F("total_records") / F("max_step_size"))
        ).annotate(
            # + 1 for call_fetch_total_records
            total_steps=F("download_tasks_count") +
                                F("total_records") + 1
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
                    then=1 + F("download_tasks_count") +
                               F("total_records") -
                                 F("records_count")
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
            phase=HarvestingPhaseEnum.RECORDS_TO_DB.value)
        hj = HarvestingJob.objects.create(
            total_records=len(objs),
        )
        for obj in objs:
            obj.job = hj

        _objs = super().bulk_create(objs=objs, *args, **kwargs)

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
