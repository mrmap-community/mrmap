from typing import Any, MutableMapping, Optional, Tuple, TypeVar

from django.db import models
from django.db.models.constraints import UniqueConstraint

T = TypeVar('T')


class UniqueConstraintDefaultValueManager(models.Manager):
    """ Custom manager which provides a custom get_or_create

    Iterates over the model meta constraint list, filtered by the type 'UniqueConstraint'
    to correctly use get_or_create
    """

    def get_or_create(self, defaults: Optional[MutableMapping[str, Any]] = None, **kwargs: Any) -> Tuple[T, bool]:
        for constraint in list(filter(lambda constraint: isinstance(constraint, UniqueConstraint), self.model._meta.constraints)):
            for field in constraint.fields:
                kwargs.update({
                    field: kwargs.get(field, self.model._meta.get_field(field).get_default()),
                })
        return super().get_or_create(defaults=defaults, **kwargs)
