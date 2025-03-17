from django.db import models, transaction
from django.db.models import Case, Count, F, Q, Value, When
from django.db.models.functions import Ceil, Round
from extras.managers import DefaultHistoryManager


class HarvestingJobManager(DefaultHistoryManager):

    def with_process_info(self):
        qs = self.get_queryset()

        qs = qs.annotate(
            unhandled_records_count=Count("temporary_md_metadata_file"),
            download_tasks_count=Ceil(
                F("total_records") / F("service__max_step_size"))
        ).annotate(
            # + 1 for call_fetch_total_records
            total_steps=F("download_tasks_count") +
                                F("total_records") + 1
        ).annotate(
            done_steps=Case(
                When(
                    condition=Q(
                        background_process__phase__icontains="Harvesting is running..."),
                    then=1 + F("unhandled_records_count")
                ),
                When(
                    condition=Q(
                        background_process__phase__icontains="parse and store ISO Metadatarecords to db..."),
                    then=1 + F("download_tasks_count") +
                               F("total_records") -
                                 F("unhandled_records_count")
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
        from registry.tasks.harvest import \
            call_md_metadata_file_to_db  # to avoid circular import errors

        _objs = super().bulk_create(objs=objs, *args, **kwargs)

        for obj in _objs:
            request = obj.job._http_request()
            transaction.on_commit(
                lambda: call_md_metadata_file_to_db.delay(
                    md_metadata_file_id=obj.pk,
                    harvesting_job_id=obj.job.pk,  # to provide the job id for TaskResult db objects
                    http_request=request,
                    background_process_pk=obj.job.background_process_id if obj.job.background_process_id else None
                ))

        return _objs
