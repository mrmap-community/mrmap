"""
Core models to implement the possibility of ACLs
"""
from uuid import uuid4

from django.contrib.auth.models import Group
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _


class ObjectRelation(models.Model):
    """Helper Model to implement GenericManyToMany relation between AccessControlList and secured_objects.

    We disable editing of all fields, cause we won't implement logic to handle updating this instances.
    """
    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    object_pk = models.CharField(_('object ID'), max_length=255, editable=False)
    content_object = GenericForeignKey(fk_field='object_pk')
    content_type = models.ForeignKey(to=ContentType, on_delete=models.CASCADE, editable=False)

    class Meta:
        """One object is unique by combing pk and ContentType. So we prevent from duplicate object entries here."""
        constraints = [
            models.UniqueConstraint(fields=['object_pk', 'content_type'], name='%(app_label)s_%(class)s_unique_together')
        ]

    def __str__(self):
        return self.content_object.__str__()


class AccessControlList(Group):
    """

    """
    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    secured_objects = models.ManyToManyField(to=ObjectRelation, blank=True)
