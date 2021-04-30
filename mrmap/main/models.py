from uuid import uuid4
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.urls import reverse
from crum import get_current_user


class GenericUriMixin:

    def get_absolute_url(self) -> str:
        return reverse(f'{self._meta.app_label}:{self.__class__.__name__.lower()}_view', args=[self.pk, ])

    def get_change_url(self) -> str:
        return reverse(f'{self._meta.app_label}:{self.__class__.__name__.lower()}_change', args=[self.pk, ])

    def get_delete_url(self) -> str:
        return reverse(f'{self._meta.app_label}:{self.__class__.__name__.lower()}_delete', args=[self.pk, ])


class UuidPk(models.Model):
    """
    An abstract model which adds uuid as primary key
    """
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)

    class Meta:
        abstract = True

    def __str__(self):
        return str(self.pk)


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
                                        #editable=False,
                                        blank=True, null=True,
                                        related_name="%(app_label)s_%(class)s_created_by_user",
                                        on_delete=models.SET_NULL)
    owned_by_org = models.ForeignKey(settings.GUARDIAN_ROLES_OWNER_MODEL,
                                     verbose_name=_('Owner'),
                                     help_text=_('The organization which is the owner of this object.'),
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
                                         #editable=False,
                                         related_name="%(app_label)s_%(class)s_last_modified_by",
                                         on_delete=models.SET_NULL)

    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        super(CommonInfo, self).__init__(*args, **kwargs)
        self._owned_by_org = self.owned_by_org

    def save(self, user=None, update_last_modified=True, owner=None, *args, **kwargs):
        if self._state.adding:
            user = get_current_user()
            self.created_by_user = user
            self.last_modified_by = user
        else:
            if update_last_modified:
                # We always want to have automatically the last timestamp from the latest change!
                # ONLY if the function is especially called with a False flag in update_last_modified, we will not change
                # the record's last change
                self.last_modified_by = get_current_user()
                self.last_modified_at = timezone.now()

        super(CommonInfo, self).save(*args, **kwargs)
