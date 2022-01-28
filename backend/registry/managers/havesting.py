from django.db import models, transaction
from django.db.models.functions import Coalesce


class TemporaryMdMetadataFileManager(models.Manager):

    def bulk_create_with_task_scheduling(self, objs, *args, **kwargs):
        from registry.tasks.harvest import \
            temporary_md_metadata_file_to_db  # to avoid circular import errors

        _objs = super().bulk_create(objs=objs, *args, **kwargs)

        for obj in _objs:
            transaction.on_commit(
                lambda: temporary_md_metadata_file_to_db.delay(md_metadata_file_id=obj.pk))

        return _objs
