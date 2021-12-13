from celery import current_task
from crum import get_current_user
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group
from django.db import models
from django.urls import reverse
from django.urls.exceptions import NoReverseMatch
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from extras.utils import camel_to_snake


class GenericModelMixin:
    """
    Mixin class to generate urls for view, change and delete action by using the current app_label of the model, the
    class name and the action which is performed by the url.

    :Example:

    - reverse('auth:organization_view', args=[self.pk,]) to get the detail view url of an organization for example.

    - reverse('auth:organization_change', args=[self.pk,]) to get the change view url of an organization for example.

    .. note::
        configure the path names in urls.py with the users `classname_action`.

        :Example:

        app_name = 'users'
        urlpatterns = [
            ...
            path('organizations/<pk>', OrganizationDetailView.as_view(), name='organization_view'),
            ...
        ]

    """

    @classmethod
    def get_add_url(cls) -> str:
        instance = cls()
        try:
            return reverse(
                f"{instance._meta.app_label}:{camel_to_snake(instance.__class__.__name__)}_add"
            )
        except NoReverseMatch:
            return ""

    def get_absolute_url(self) -> str:
        try:
            return reverse(
                f"{self._meta.app_label}:{camel_to_snake(self.__class__.__name__)}_view",
                args=[
                    self.pk,
                ],
            )
        except NoReverseMatch:
            return self.get_concrete_table_url()

    @classmethod
    def get_table_url(cls) -> str:
        instance = cls()
        try:
            return reverse(
                f"{instance._meta.app_label}:{camel_to_snake(instance.__class__.__name__)}_list"
            )
        except NoReverseMatch:
            return ""

    def get_concrete_table_url(self) -> str:
        try:
            return (
                reverse(
                    f"{self._meta.app_label}:{camel_to_snake(self.__class__.__name__)}_list"
                )
                + f"?id__in={self.pk}"
            )
        except NoReverseMatch:
            return ""

    def get_change_url(self) -> str:
        try:
            return reverse(
                f"{self._meta.app_label}:{camel_to_snake(self.__class__.__name__)}_change",
                args=[
                    self.pk,
                ],
            )
        except NoReverseMatch:
            return ""

    def get_delete_url(self) -> str:
        try:
            return reverse(
                f"{self._meta.app_label}:{camel_to_snake(self.__class__.__name__)}_delete",
                args=[
                    self.pk,
                ],
            )
        except NoReverseMatch:
            return ""

    def get_restore_url(self) -> str:
        try:
            return reverse(
                f"{self._meta.app_label}:{camel_to_snake(self.__class__.__name__)}_restore",
                args=[
                    self.pk,
                ],
            )
        except NoReverseMatch:
            return ""

    def get_xml_view_url(self) -> str:
        try:
            return reverse(
                f"{self._meta.app_label}:{camel_to_snake(self.__class__.__name__)}_xml_view",
                args=[self.pk],
            )
        except NoReverseMatch:
            return ""


class CommonInfo(models.Model):
    """
    An abstract model which adds fields to store the creation and last-updated times for an object. All fields can be
    null to facilitate adding these fields to existing instances via a database migration.
    """

    created_at = models.DateTimeField(
        verbose_name=_("Created at"),
        help_text=_("The timestamp of the creation date of this object."),
        auto_now_add=True,
        editable=False,
        blank=True,
        db_index=True,
    )
    created_by_user = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        verbose_name=_("Created by"),
        help_text=_("The user who has created this object."),
        editable=False,
        blank=True,
        null=True,
        related_name="%(app_label)s_%(class)s_created_by_user",
        on_delete=models.SET_NULL,
    )
    owner = models.ForeignKey(
        to=Group,
        verbose_name=_("Owner"),
        help_text=_("The organization which is the owner of this object."),
        editable=False,
        blank=True,
        null=True,
        related_name="%(app_label)s_%(class)s_owner",
        on_delete=models.SET_NULL,
    )
    last_modified_at = models.DateTimeField(
        verbose_name=_("Last modified at"),
        help_text=_("The timestamp of the last modification of this object"),
        editable=False,
        auto_now=True,
        db_index=True,
    )
    last_modified_by = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        verbose_name=_("Last modified by"),
        help_text=_("The last user who has modified this object."),
        blank=True,
        null=True,
        editable=False,
        related_name="%(app_label)s_%(class)s_last_modified_by",
        on_delete=models.SET_NULL,
    )

    class Meta:
        abstract = True
        get_latest_by = "created_at"
        ordering = ["-created_at", ]

    def save(self, update_last_modified=True, current_user=None, *args, **kwargs):
        if current_task and not current_user:
            # running inside celery worker with non safe access to thread locals.
            # FIXME: find a easy solution to pass in the current_user
            pass
        else:
            # try to fetch the current user from thread variable
            current_user = get_current_user()
            if isinstance(current_user, AnonymousUser):
                current_user = get_user_model().objects.get(username="AnonymousUser")

        if self._state.adding:
            self.created_by_user = current_user
            self.last_modified_by = current_user
        else:
            if update_last_modified:
                # We always want to have automatically the last timestamp from the latest change!
                # ONLY if the function is especially called with a False flag in update_last_modified, we will not
                # change the record's last change
                self.last_modified_by = current_user
                self.last_modified_at = timezone.now()

        super(CommonInfo, self).save(*args, **kwargs)
