from django.db import models


class DocumentManager(models.Manager):
    """ todo"""

    def bulk_create(self, create_custom_copy=True, *args, **kwargs):
        """
            todo
        """
        _objs = super().bulk_create(*args, **kwargs)
        if create_custom_copy:
            custom_objs = []
            for obj in _objs:
                custom_objs.append(self.model(**obj.get_copy_fields_dict()))
            self.bulk_create(create_custom_copy=False, objs=custom_objs)
        return _objs
