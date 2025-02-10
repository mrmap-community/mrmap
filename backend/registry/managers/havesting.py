from django.db import models, transaction


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
