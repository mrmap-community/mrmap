"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 28.05.19

"""
import uuid

from django.db import models
from django.urls import reverse
from django_bootstrap_swt.components import LinkButton, Tag
from django_bootstrap_swt.enums import ButtonColorEnum

from MrMap.icons import IconEnum
from service.models import Metadata
from structure.models import MrMapUser
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _l

from structure.permissionEnums import PermissionEnum


class Subscription(models.Model):
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

    def get_absolute_url(self):
        return reverse('manage_subscriptions')

    def get_edit_url(self):
        return reverse('edit_subscription', args=[self.id])

    def get_delete_url(self):
        return reverse('delete_subscription', args=[self.id])

    def get_actions(self):
        return [LinkButton(url=self.get_edit_url(),
                           content=Tag(tag='i', attrs={"class": [IconEnum.EDIT.value]}).render(),
                           color=ButtonColorEnum.WARNING,
                           tooltip=_l(f"Edit subscription"), ),
                LinkButton(url=self.get_delete_url(),
                           content=Tag(tag='i', attrs={"class": [IconEnum.DELETE.value]}).render(),
                           color=ButtonColorEnum.DANGER,
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