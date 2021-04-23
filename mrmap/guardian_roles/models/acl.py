"""
Core models to implement the possibility of ACLs
"""
from uuid import uuid4

from django.contrib.auth.models import Group
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _

from main.models import CommonInfo


class GenericObjectRelation(models.Model):
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


class AccessControlList(Group, CommonInfo):
    """

    """
    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    description = models.CharField(max_length=256, null=True, blank=True)
    secured_objects = models.ManyToManyField(to=GenericObjectRelation, blank=True)

    def add_secured_object(self, secured_object):
        _secured_object = GenericObjectRelation.objects.create(object_pk=secured_object.pk,
                                                               content_type=ContentType.objects.get_for_model(secured_object))
        self.secured_objects.add(_secured_object)

    def add_secured_objects(self, secured_objects):
        _secured_objects = []
        for secured_object in secured_objects:
            _secured_objects.append(GenericObjectRelation(object_pk=secured_object.pk,
                                                          content_type=ContentType.objects.get_for_model(secured_object)))
        GenericObjectRelation.objects.bulk_create(objs=_secured_objects)
        self.secured_objects.add(*_secured_objects)
