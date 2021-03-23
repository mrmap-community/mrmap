from uuid import uuid4
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from main.middleware import CurrentUserMiddleware
from django.utils import timezone


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
    created_at = models.DateTimeField(verbose_name='Created at',
                                      auto_now_add=True,
                                      db_index=True)
    created_by_user = models.ForeignKey(settings.AUTH_USER_MODEL,
                                        verbose_name='Created by',
                                        blank=True, null=True,
                                        related_name="%(app_label)s_%(class)s_created",
                                        on_delete=models.SET_NULL)
    owned_by_org = models.ForeignKey(settings.OWNER_MODEL,
                                     verbose_name=_('Owner'),
                                     blank=True, null=True,
                                     related_name="%(app_label)s_%(class)s_owned",
                                     on_delete=models.SET_NULL)
    last_modified_at = models.DateTimeField(verbose_name='Last modified at',
                                            auto_now=True,
                                            db_index=True)
    last_modified_by = models.ForeignKey(settings.AUTH_USER_MODEL,
                                         verbose_name='Last modified by',
                                         blank=True, null=True,
                                         related_name="%(app_label)s_%(class)s_lastmodified",
                                         on_delete=models.SET_NULL)

    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        super(CommonInfo, self).__init__(*args, **kwargs)
        self._owned_by_org = self.owned_by_org

    @staticmethod
    def get_current_user():
        return CurrentUserMiddleware.get_current_user()

    def set_user_specific_fields(self, user, owner):
        """
        Set user-related fields before saving the instance.
        If no user with a primary key is given the fields are not
        set.
        """
        if user and user.pk:
            if self._state.adding:
                self.created_by_user = user
                self.owned_by_org = owner if owner else user.organization
            self.last_modified_by = user

    def save(self, user=None, update_last_modified=True, owner=None, *args, **kwargs):
        if update_last_modified:
            # We always want to have automatically the last timestamp from the latest change!
            # ONLY if the function is especially called with a False flag in update_last_modified, we will not change
            # the record's last change
            self.last_modified_at = timezone.now()
        self.set_user_specific_fields(user=user if user else self.get_current_user(), owner=owner)
        super(CommonInfo, self).save(*args, **kwargs)
