"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 28.05.19

"""
from django import forms
from django.core.exceptions import ObjectDoesNotExist
from django.template.loader import render_to_string
from django.urls import reverse, resolve
from django.utils.translation import gettext_lazy as _

from MrMap.forms import MrMapForm, MrMapModelForm, MrMapConfirmForm
from MrMap.messages import EMAIL_IS_UNKNOWN, PASSWORD_CHANGE_OLD_PASSWORD_WRONG
from MrMap.responses import DefaultContext
from MrMap.settings import MIN_PASSWORD_LENGTH
from MrMap.validators import PASSWORD_VALIDATORS, USERNAME_VALIDATORS
from service.helper.enums import MetadataEnum
from service.models import Metadata
from structure.models import MrMapUser, Theme
from users.models import Subscription


class PasswordResetForm(forms.Form):
    email = forms.EmailField(max_length=255, required=True, label=_("E-Mail"), label_suffix="")

    def clean(self):
        cleaned_data = super(PasswordResetForm, self).clean()
        email = cleaned_data.get("email")
        try:
            MrMapUser.objects.get(email=email)
        except ObjectDoesNotExist:
            self.add_error("email", forms.ValidationError(EMAIL_IS_UNKNOWN))

        return cleaned_data


class PasswordChangeForm(forms.Form):
    user = None

    old_password = forms.CharField(
        max_length=255,
        label=_("Old password"),
        label_suffix=" ",
        widget=forms.PasswordInput,
    )
    new_password = forms.CharField(
        min_length=MIN_PASSWORD_LENGTH,
        max_length=255,
        label=_("New password"),
        label_suffix=" ",
        widget=forms.PasswordInput,
        validators=PASSWORD_VALIDATORS
    )
    new_password_again = forms.CharField(
        max_length=255,
        label=_("Confirm new Password"),
        label_suffix=" ",
        widget=forms.PasswordInput,
    )

    def __init__(self, *args, **kwargs):

        # pop custom kwargs before invoke super constructor and hold them
        self.user = None if 'user' not in kwargs else kwargs.pop('user')

        # run super constructor to construct the form
        super(PasswordChangeForm, self).__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super(PasswordChangeForm, self).clean()
        old_password = cleaned_data.get("old_password")
        password = cleaned_data.get("new_password")
        password_again = cleaned_data.get("new_password_again")

        if self.user is not None and not self.user.check_password(old_password):
            self.add_error("old_password", forms.ValidationError(PASSWORD_CHANGE_OLD_PASSWORD_WRONG))

        if password != password_again:
            self.add_error("new_password_again", forms.ValidationError(_("Password and confirmed password does not match")))

        return cleaned_data


class UserForm(forms.ModelForm):
    theme = forms.ModelChoiceField(queryset=Theme.objects.all(), to_field_name='name', empty_label=None, required=False)

    class Meta:
        model = MrMapUser
        fields = [
            "first_name",
            "last_name",
            "email",
            "confirmed_newsletter",
            "confirmed_survey",
            "theme",
        ]


class SubscriptionForm(MrMapModelForm):
    metadata = forms.ModelChoiceField(
        label=_("Service"),
        help_text=_("Select the service you want to subscribe. When you edit an existing subscription, you can not change this selection."),
        queryset=Metadata.objects.filter(
            metadata_type__type=MetadataEnum.SERVICE.value,
            is_active=True,
        )
    )

    class Meta:
        model = Subscription
        fields = [
            "metadata",
            "notify_on_update",
            "notify_on_metadata_edit",
            "notify_on_access_edit",
        ]
        help_texts = {
            "notify_on_update": _("Sends an e-mai if the service has been updated."),
            "notify_on_access_edit": _("Sends an e-mai if the service's access has been changed."),
            "notify_on_metadata_edit": _("Sends an e-mai if the service's metadata has been changed."),
        }
        labels = {
            "notify_on_update": _("Notify on update"),
            "notify_on_access_edit": _("Notify on access changes"),
            "notify_on_metadata_edit": _("Notify on metadata changes"),
        }

    def __init__(self, is_edit: bool = False, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if is_edit:
            # Prevent user from changing the subscribed metadata itself
            self.fields['metadata'].disabled = True


class SubscriptionRemoveForm(MrMapConfirmForm):
    def __init__(self, *args, **kwargs):
        super().__init__(is_confirmed_label=_('Do you realy want to remove this subscription?'), *args, **kwargs)
