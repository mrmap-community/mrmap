from django.db import models


class DocumentManager(models.Manager):
    """ todo"""

    def bulk_create(self, objs, *args, **kwargs):
        """
            todo
        """
        for obj in objs:
            obj.content_backup = obj.content
        _objs = super().bulk_create(*args, **kwargs)
        return _objs
