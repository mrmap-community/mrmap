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
    """
    Helper Model to implement GenericManyToMany relation between AccessControlList and secured_objects.

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
    Access control list model to store group based lists of users with sets of permissions and objects which shall
    be accessible.
    """
    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    description = models.CharField(max_length=256, null=True, blank=True)
    accessible_objects = models.ManyToManyField(to=GenericObjectRelation, blank=True)
    default_acl = models.BooleanField(default=False)

    def add_accessible_object(self, accessible_object):
        """
        helper method to generate GenericObjectRelation object or get them if they exist and adds them to the
        accessible_objects list.
        """
        _accessible_object, created = GenericObjectRelation.objects.get_or_create(object_pk=accessible_object.pk,
                                                                                  content_type=ContentType.objects.get_for_model(accessible_object))
        self.accessible_objects.add(_accessible_object)

    def add_accessible_objects(self, accessible_objects):
        """
        helper method to generate GenericObjectRelation objects, generates them in bulk mode and adds them to the
        accessible_objects list.
        """
        _accessible_object = []
        for accessible_object in accessible_objects:
            _accessible_object.append(GenericObjectRelation(object_pk=accessible_object.pk,
                                                            content_type=ContentType.objects.get_for_model(accessible_object)))
        GenericObjectRelation.objects.bulk_create(objs=_accessible_object)
        self.accessible_objects.add(*_accessible_object)
