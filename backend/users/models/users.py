import hashlib
import uuid
import six
from django.db.models import Q, QuerySet
from django.utils.functional import cached_property
from acls.models.acls import AccessControlList
from extras.models import CommonInfo, GenericModelMixin
from django.contrib.auth.hashers import get_hasher
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from MrMap.icons import IconEnum, get_icon
from users.models.groups import Organization
from users.settings import USER_ACTIVATION_TIME_WINDOW


class MrMapUser(AbstractUser):
    id = models.UUIDField(primary_key=True,
                          default=uuid.uuid4,
                          editable=False)
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

    def get_absolute_url(self):
        return reverse('users:password_change_done')

    def get_edit_view_url(self):
        return reverse('users:edit_profile')

    @cached_property
    def organizations(self):
        return Organization.objects.prefetch_related('acls_accesscontrollist_owned_by_org',
                                                     'acls_accesscontrollist_owned_by_org__user_set',
                                                     'acls_accesscontrollist_owned_by_org__permissions')\
            .filter(acls_accesscontrollist_owned_by_org__permissions__codename='view_organization')\
            .distinct('name')

    def get_publishable_organizations(self):
        if self.is_superuser:
            return Organization.objects.all()
        else:
            organizations = Organization.objects.\
                filter(acls_accesscontrollist_owned_by_org__in=AccessControlList.objects.
                       filter(user=self, permissions__codename='add_resource'))\
                .prefetch_related('can_publish_for')
            for org in organizations:
                organizations |= org.can_publish_for.all()
            return organizations.distinct('name', 'pk')

    def get_instances(self, klass, filter: Q = None, perms: str = None, accept_global_perms: bool = False) -> QuerySet:
        from guardian.shortcuts import get_objects_for_user
        if not perms:
            perms = f'{klass._meta.app_label}.view_{klass._meta.object_name.lower()}'
        if filter:
            queryset = klass.objects.filter(filter)
        else:
            queryset = klass.objects.all()
        return get_objects_for_user(user=self,
                                    perms=perms,
                                    klass=queryset,
                                    accept_global_perms=accept_global_perms)

    def create_activation(self):
        """ Create an activation object

        Returns:
             nothing
        """
        # user does not exist yet! We need to create an activation object
        user_activation = UserActivation()
        user_activation.user = self
        user_activation.activation_until = timezone.now() + timezone.timedelta(hours=USER_ACTIVATION_TIME_WINDOW)
        hasher = get_hasher('default')
        user_activation.activation_hash = hashlib.sha256(
            self.username + hasher.salt() + str(user_activation.activation_until))
        user_activation.save()


class UserActivation(models.Model, PasswordResetTokenGenerator):
    user = models.OneToOneField(MrMapUser, null=False, blank=False, on_delete=models.CASCADE)
    activation_until = models.DateTimeField(null=False, blank=False)
    activation_hash = models.CharField(primary_key=True, max_length=500)

    def __str__(self):
        return self.user.username

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        if self._state.adding:
            if not self.activation_until:
                self.activation_until = timezone.now() + timezone.timedelta(days=USER_ACTIVATION_TIME_WINDOW)
            self.activation_hash = self.make_token(self.user)
        super().save(force_insert, force_update, using, update_fields)

    def _make_hash_value(self, user, timestamp):
        return (six.text_type(user.pk) + six.text_type(timestamp) +
                six.text_type(user.email))


# todo: check if subscription should be part of users app?
class Subscription(GenericModelMixin, CommonInfo):
    id = models.UUIDField(primary_key=True,
                          default=uuid.uuid4)
    web_map_service = models.ForeignKey(to='registry.WebMapService',
                                        null=True,
                                        blank=True,
                                        on_delete=models.CASCADE,
                                        verbose_name=_('web map service'),
                                        help_text=_("Select the service you want to subscribe. When you edit an existing "
                                                    "subscription, you can not change this selection."))
    web_feature_service = models.ForeignKey(to='registry.WebFeatureService',
                                            null=True,
                                            blank=True,
                                            on_delete=models.CASCADE,
                                            verbose_name=_('web feature service'),
                                            help_text=_("Select the service you want to subscribe. When you edit an existing "
                                                        "subscription, you can not change this selection."))
    user = models.ForeignKey(to=MrMapUser,
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
        unique_together = ('web_map_service', 'web_feature_service', 'user',)

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
