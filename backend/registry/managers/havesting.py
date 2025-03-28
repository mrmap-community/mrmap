from celery import chord
from django.db import models, transaction
from django.db.models import Case, Count, F, Q, Value, When
from django.db.models.functions import Ceil, Round
from django.utils.timezone import now
from django_cte import CTEManager
from extras.managers import DefaultHistoryManager
from notify.tasks import finish_background_process


class HarvestingJobManager(DefaultHistoryManager, CTEManager):

    def with_process_info(self):
        qs = self.get_queryset()

        qs = qs.annotate(
            unhandled_records_count=Count("temporary_md_metadata_file"),
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
                        background_process__phase__icontains="Harvesting is running..."),
                    then=1 + Ceil(F("unhandled_records_count") /
                                  F("max_step_size"))
                ),
                When(
                    condition=Q(
                        background_process__phase__icontains="parse and store ISO Metadatarecords to db..."),
                    then=1 + F("download_tasks_count") +
                               F("total_records") -
                                 F("unhandled_records_count")
                ),
                When(
                    condition=Q(
                        background_process__phase__icontains="completed"),
                    then=F("total_steps")
                ),
                default=0
            )
        ).annotate(
            progress=Case(
                When(
                    ~Q(background_process__phase="abort") & Q(
                        background_process__done_at__isnull=False),
                    then=Value(100.0)
                ),
                default=Case(
                    When(
                        total_steps__gt=0,
                        then=Round(F("done_steps") * 1.0 / F("total_steps") * 100.0, precission=2),  # noqa

                    ),
                    default=0.0
                ),
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
            phase='parse and store ISO Metadatarecords to db...')
        hj = HarvestingJob.objects.create(
            total_records=len(objs),
            background_process=bp)
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
                lambda: chord(to_db_tasks)(finish_background_process.s(
                    http_request=request,
                    background_process_pk=bp.pk
                ))
            )
        else:
            BackgroundProcess.objects.filter(pk=bp.pk).update(
                phase='completed',
                done_at=now(),
                done_steps=F('total_steps')
            )

        return db_objs
