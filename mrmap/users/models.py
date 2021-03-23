"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 28.05.19

"""
import uuid
import six
from django.db.models import Q
from guardian.shortcuts import get_objects_for_user

from main.models import CommonInfo
from service.models import Metadata
from django.utils.translation import gettext_lazy as _l
from django.contrib.auth.hashers import get_hasher
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_bootstrap_swt.components import LinkButton, Tag
from django_bootstrap_swt.enums import ButtonColorEnum, ButtonSizeEnum
from MrMap.icons import IconEnum, get_icon
from service.helper.crypto_handler import CryptoHandler
from structure.models import Organization
from structure.settings import USER_ACTIVATION_TIME_WINDOW
from users.settings import default_activation_time


class MrMapUser(AbstractUser):
    id = models.UUIDField(primary_key=True,
                          default=uuid.uuid4,
                          editable=False)
    # todo: handle organization deletion, what should happen with the users?
    organization = models.ForeignKey(Organization,
                                     related_name='user_set',
                                     on_delete=models.SET_NULL,
                                     null=True,
                                     blank=True)
    confirmed_newsletter = models.BooleanField(default=False,
                                               verbose_name=_("I want to sign up for the newsletter"))
    confirmed_survey = models.BooleanField(default=False,
                                           verbose_name=_("I want to participate in surveys"))
    confirmed_dsgvo = models.DateTimeField(auto_now_add=True,
                                           verbose_name=_("I understand and accept that my data will be automatically "
                                                          "processed and securely stored, as it is stated in the "
                                                          "general data protection regulation (GDPR)."))

    class Meta:
        verbose_name = _('User')
        verbose_name_plural = _('Users')

    @property
    def icon(self):
        return get_icon(IconEnum.USER)

    def __str__(self):
        return self.username

    def get_absolute_url(self):
        return reverse('password_change_done')

    def get_edit_view_url(self):
        return reverse('edit_profile')

    @property
    def invite_to_group_url(self):
        return f"{reverse('structure:group_invitation_request_new')}?user={self.id}"

    def get_publishable_organizations(self, include_self=True):
        if self.is_superuser:
            return Organization.objects.filter(is_auto_generated=False)
        return self.organization.get_publishable_organizations(include_self=include_self) if self.organization \
            else Organization.objects.none()

    def get_instances(self, klass, filter: Q = None, perms: str = None):
        if not perms:
            perms = f'{klass._meta.app_label}.view_{klass._meta.object_name.lower()}'
        if filter:
            queryset = klass.objects.filter(filter)
        else:
            queryset = klass.objects.all()
        return get_objects_for_user(user=self,
                                    perms=perms,
                                    klass=queryset)

    def create_activation(self):
        """ Create an activation object

        Returns:
             nothing
        """
        # user does not exist yet! We need to create an activation object
        user_activation = UserActivation()
        user_activation.user = self
        user_activation.activation_until = timezone.now() + timezone.timedelta(hours=USER_ACTIVATION_TIME_WINDOW)
        sec_handler = CryptoHandler()
        hasher = get_hasher('default')
        user_activation.activation_hash = sec_handler.sha256(
            self.username + hasher.salt() + str(user_activation.activation_until))
        user_activation.save()


class UserActivation(models.Model, PasswordResetTokenGenerator):
    user = models.OneToOneField(MrMapUser, null=False, blank=False, on_delete=models.CASCADE)
    activation_until = models.DateTimeField(default=timezone.now() + timezone.timedelta(days=default_activation_time))
    activation_hash = models.CharField(primary_key=True, max_length=500)

    def __str__(self):
        return self.user.username

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        if self._state.adding:
            self.activation_hash = self.make_token(self.user)
        super().save(force_insert, force_update, using, update_fields)

    def _make_hash_value(self, user, timestamp):
        return (
                six.text_type(user.pk) + six.text_type(timestamp) +
                six.text_type(user.email)
        )


class Subscription(CommonInfo):
    id = models.UUIDField(primary_key=True,
                          default=uuid.uuid4)
    metadata = models.ForeignKey(Metadata, on_delete=models.CASCADE,
                                 verbose_name=_('Service'),
                                 help_text=_("Select the service you want to subscribe. When you edit an existing "
                                             "subscription, you can not change this selection."))
    user = models.ForeignKey(MrMapUser,
                             on_delete=models.CASCADE)
    notify_on_update = models.BooleanField(default=True,
                                           verbose_name=_('Notify on update'),
                                           help_text=_("Sends an e-mai if the service has been updated."))
    notify_on_metadata_edit = models.BooleanField(default=True,
                                                  verbose_name=_('Notify on metadata edit'),
                                                  help_text=_("Sends an e-mai if the service's metadata has been "
                                                              "changed."))
    notify_on_access_edit = models.BooleanField(default=True,
                                                verbose_name=_('Notify on access edit'),
                                                help_text=_("Sends an e-mai if the service's access has been changed."))
    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        # It shall be restricted to create multiple subscription objects for the same service per user. This unique
        # constraint will also raise an form error if a user trays to add duplicates.
        unique_together = ('metadata', 'user',)

    @property
    def icon(self):
        return get_icon(IconEnum.SUBSCRIPTION)

    def get_absolute_url(self):
        return reverse('manage_subscriptions')

    @classmethod
    def get_add_view_url(cls):
        return reverse('add_subscription')

    def get_edit_view_url(self):
        return reverse('edit_subscription', args=[self.id])

    def get_delete_view_url(self):
        return reverse('delete_subscription', args=[self.id])

    def get_actions(self):
        return [LinkButton(url=self.get_edit_view_url(),
                           content=Tag(tag='i', attrs={"class": [IconEnum.EDIT.value]}).render(),
                           color=ButtonColorEnum.WARNING,
                           size=ButtonSizeEnum.SMALL,
                           tooltip=_l(f"Edit subscription"), ),
                LinkButton(url=self.get_delete_view_url(),
                           content=Tag(tag='i', attrs={"class": [IconEnum.DELETE.value]}).render(),
                           color=ButtonColorEnum.DANGER,
                           size=ButtonSizeEnum.SMALL,
                           tooltip=_l(f"Delete subscription"), )]

    def inform_subscriptor(self):
        """ Informs subscriptor on changes

        Returns:

        """
        self._inform_subscriptor_update()
        self._inform_subscriptor_metadata_edit()
        self._inform_subscriptor_access_edit()

    # Add django signal to call
    def _inform_subscriptor_update(self):
        """ Informs subscriptor on updates

        Returns:

        """
        if self.notify_on_update:
            # ToDo: Send Mail!
            pass

    # Add django signal to call
    def _inform_subscriptor_metadata_edit(self):
        """ Informs subscriptor on metadata changes

        Returns:

        """
        if self.notify_on_metadata_edit:
            # ToDo: Send Mail!
            pass

    # Add django signal to call
    def _inform_subscriptor_access_edit(self):
        """ Informs subscriptor on access changes

        Returns:

        """
        if self.notify_on_access_edit:
            # ToDo: Send Mail!
            pass
