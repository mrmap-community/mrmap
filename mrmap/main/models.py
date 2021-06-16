import re
import threading

from uuid import uuid4
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.urls import reverse
from django.urls.exceptions import NoReverseMatch
from crum import get_current_user
from MrMap.icons import get_icon, IconEnum
from main.utils import camel_to_snake

_thread_locals = threading.local()


class GenericFKSaveMixin:
    """Class to support a generic way of first follow all unsaved ForeignKey fields.

       We need this for models we parse from xml or some other stuff.
    """
    def save(self, *args, **kwargs):
        """ generic way to save all fk fields first """
        for field in self._meta.fields:
            if field.get_internal_type() == 'ForeignKey':
                _field = getattr(self, field.name)
                if _field:
                    _field.save()
        super().save(*args, **kwargs)


class GenericModelMixin:
    """
    Mixin class to generate urls for view, change and delete action by using the current app_label of the model, the
    class name and the action which is performed by the url.

    :Example:

    - reverse('structure:organization_view', args=[self.pk,]) to get the detail view url of an organization for example.

    - reverse('structure:organization_change', args=[self.pk,]) to get the change view url of an organization for example.

    .. note::
        configure the path names in urls.py with the structure `classname_action`.

        :Example:

        app_name = 'structure'
        urlpatterns = [
            ...
            path('organizations/<pk>', OrganizationDetailView.as_view(), name='organization_view'),
            ...
        ]

    """

    @property
    def icon(self):
        try:
            return get_icon(getattr(IconEnum, self.__class__.__name__.upper()))
        except AttributeError:
            return ""

    def get_absolute_url(self) -> str:
        try:
            return reverse(f'{self._meta.app_label}:{camel_to_snake(self.__class__.__name__)}_view', args=[self.pk, ])
        except NoReverseMatch:
            return ""

    def get_table_url(self) -> str:
        try:
            return reverse(
                f'{self._meta.app_label}:{camel_to_snake(self.__class__.__name__)}_list') + f'?id__in={self.pk}'
        except NoReverseMatch:
            return ""

    def get_change_url(self) -> str:
        try:
            return reverse(f'{self._meta.app_label}:{camel_to_snake(self.__class__.__name__)}_change', args=[self.pk, ])
        except NoReverseMatch:
            return ""

    def get_delete_url(self) -> str:
        try:
            return reverse(f'{self._meta.app_label}:{camel_to_snake(self.__class__.__name__)}_delete', args=[self.pk, ])
        except NoReverseMatch:
            return ""

    def get_restore_url(self) -> str:
        try:
            return reverse(f'{self._meta.app_label}:{camel_to_snake(self.__class__.__name__)}_restore', args=[self.pk, ])
        except NoReverseMatch:
            return ""

    def get_xml_view_url(self) -> str:
        try:
            return reverse(f'{self._meta.app_label}:{camel_to_snake(self.__class__.__name__)}_xml_view', args=[self.pk])
        except NoReverseMatch:
            return ""


class UuidPk(models.Model):
    """
    An abstract model which adds uuid as primary key
    """
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)

    class Meta:
        abstract = True

    def __str__(self):
        return str(self.pk)


def set_current_owner(owner):
    """
        .. note:
            be carefully of using _thread_locals with celery. Celery worker threads are endless running.
    """
    _thread_locals.owner = owner


def get_current_owner():
    """
        .. note:
            be carefully of using _thread_locals with celery. Celery worker threads are endless running.
    """
    return getattr(_thread_locals, 'owner', None)


class CommonInfo(models.Model):
    """
    An abstract model which adds fields to store the creation and last-updated times for an object. All fields can be
    null to facilitate adding these fields to existing instances via a database migration.
    """
    created_at = models.DateTimeField(verbose_name=_('Created at'),
                                      help_text=_('The timestamp of the creation date of this object.'),
                                      auto_now_add=True,
                                      editable=False,
                                      db_index=True)
    created_by_user = models.ForeignKey(settings.AUTH_USER_MODEL,
                                        verbose_name=_('Created by'),
                                        help_text=_('The user who has created this object.'),
                                        editable=False,
                                        blank=True, null=True,
                                        related_name="%(app_label)s_%(class)s_created_by_user",
                                        on_delete=models.SET_NULL)
    owned_by_org = models.ForeignKey(settings.GUARDIAN_ROLES_OWNER_MODEL,
                                     verbose_name=_('Owner'),
                                     help_text=_('The organization which is the owner of this object.'),
                                     editable=False,
                                     blank=True, null=True,
                                     related_name="%(app_label)s_%(class)s_owned_by_org",
                                     on_delete=models.SET_NULL)
    last_modified_at = models.DateTimeField(verbose_name=_('Last modified at'),
                                            help_text=_('The timestamp of the last modification of this object'),
                                            editable=False,
                                            auto_now=True,
                                            db_index=True)
    last_modified_by = models.ForeignKey(settings.AUTH_USER_MODEL,
                                         verbose_name=_('Last modified by'),
                                         help_text=_('The last user who has modified this object.'),
                                         blank=True, null=True,
                                         editable=False,
                                         related_name="%(app_label)s_%(class)s_last_modified_by",
                                         on_delete=models.SET_NULL)

    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        super(CommonInfo, self).__init__(*args, **kwargs)
        # self._owned_by_org_id = self.owned_by_org_id

    def save(self, update_last_modified=True, *args, **kwargs):
        if self._state.adding:
            user = get_current_user()
            self.created_by_user = user
            self.last_modified_by = user

            if not self.owned_by_org:
                # the owner is not set yet. Try to get it from the global variable
                self.owned_by_org = get_current_owner()
        else:
            if update_last_modified:
                # We always want to have automatically the last timestamp from the latest change!
                # ONLY if the function is especially called with a False flag in update_last_modified, we will not
                # change the record's last change
                self.last_modified_by = get_current_user()
                self.last_modified_at = timezone.now()

        super(CommonInfo, self).save(*args, **kwargs)
