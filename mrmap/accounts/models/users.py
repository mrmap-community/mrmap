import hashlib
import uuid

import six
from accounts.managers.users import CustomUserManager
from accounts.settings import USER_ACTIVATION_TIME_WINDOW
from django.contrib.auth.hashers import get_hasher
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from guardian.shortcuts import assign_perm


def get_settings_default():
    return {}


class User(AbstractUser):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False)
    confirmed_newsletter = models.BooleanField(
        default=False,
        verbose_name=_("I want to sign up for the newsletter"))
    confirmed_survey = models.BooleanField(
        default=False,
        verbose_name=_("I want to participate in surveys"))
    confirmed_dsgvo = models.DateTimeField(
        # FIXME: auto_now_add results in auto accepting dsgvo... this is not a good practice.
        auto_now_add=True,
        help_text=_("I understand and accept that my data will be automatically "
                    "processed and securely stored, as it is stated in the "
                    "general data protection regulation (GDPR)."))
    settings = models.JSONField(
        verbose_name=_('settings'),
        help_text=_(
            'json storage on backend to provide configurations for frontends.'),
        default=get_settings_default)

    objects = CustomUserManager()

    class Meta:
        verbose_name = _('User')
        verbose_name_plural = _('Users')

    def assign_object_perms(self):
        assign_perm(perm='view_user',
                    user_or_group=self,
                    obj=self)
        assign_perm(perm='change_user',
                    user_or_group=self,
                    obj=self)
        assign_perm(perm='delete_user',
                    user_or_group=self,
                    obj=self)

    def create_activation(self):
        """ Create an activation object

        Returns:
             nothing
        """
        # user does not exist yet! We need to create an activation object
        user_activation = UserActivation()
        user_activation.user = self
        user_activation.activation_until = timezone.now(
        ) + timezone.timedelta(hours=USER_ACTIVATION_TIME_WINDOW)
        hasher = get_hasher('default')
        user_activation.activation_hash = hashlib.sha256(
            self.username + hasher.salt() + str(user_activation.activation_until))
        user_activation.save()


class UserActivation(models.Model, PasswordResetTokenGenerator):
    user = models.OneToOneField(
        User, null=False, blank=False, on_delete=models.CASCADE)
    activation_until = models.DateTimeField(null=False, blank=False)
    activation_hash = models.CharField(primary_key=True, max_length=500)

    def __str__(self):
        return self.user.username

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        if self._state.adding:
            if not self.activation_until:
                self.activation_until = timezone.now(
                ) + timezone.timedelta(days=USER_ACTIVATION_TIME_WINDOW)
            self.activation_hash = self.make_token(self.user)
        super().save(force_insert, force_update, using, update_fields)

    def _make_hash_value(self, user, timestamp):
        return (six.text_type(user.pk) + six.text_type(timestamp) +
                six.text_type(user.email))
