"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 28.05.19

"""
from dal import autocomplete
from django import forms
from django.contrib.auth import login
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import gettext_lazy as _
from django.contrib import messages

from MrMap.forms import MrMapModelForm, MrMapConfirmForm, MrMapForm
from MrMap.messages import EMAIL_IS_UNKNOWN, PASSWORD_CHANGE_OLD_PASSWORD_WRONG, SUBSCRIPTION_ALREADY_EXISTS_TEMPLATE, \
    SUBSCRIPTION_EDITING_SUCCESSFULL, SUBSCRIPTION_EDITING_UNSUCCESSFULL, SUBSCRIPTION_REMOVED_TEMPLATE, \
    RESOURCE_NOT_FOUND_OR_NOT_OWNER, PASSWORD_CHANGE_SUCCESS, ACCOUNT_UPDATE_SUCCESS
from MrMap.settings import MIN_PASSWORD_LENGTH
from MrMap.validators import PASSWORD_VALIDATORS
from editor.forms import MetadataModelMultipleChoiceField
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


class PasswordChangeForm(MrMapForm):
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
        super(PasswordChangeForm, self).__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super(PasswordChangeForm, self).clean()
        old_password = cleaned_data.get("old_password")
        password = cleaned_data.get("new_password")
        password_again = cleaned_data.get("new_password_again")

        if self.requesting_user is not None and not self.requesting_user.check_password(old_password):
            self.add_error("old_password", forms.ValidationError(PASSWORD_CHANGE_OLD_PASSWORD_WRONG))

        if password != password_again:
            self.add_error("new_password_again", forms.ValidationError(_("Password and confirmed password does not match")))

        return cleaned_data

    def process_change_password(self):
        password = self.cleaned_data["new_password"]
        self.requesting_user.set_password(password)
        self.requesting_user.save()
        login(self.request, self.requesting_user)
        messages.add_message(self.request, messages.SUCCESS, PASSWORD_CHANGE_SUCCESS)


class UserForm(MrMapModelForm):
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

    def process_account_change(self):
        # save changes
        user = self.save()
        user.save()
        messages.add_message(self.request, messages.SUCCESS, ACCOUNT_UPDATE_SUCCESS)


class SubscriptionForm(MrMapModelForm):
    metadata = forms.ModelChoiceField(
        label=_("Service"),
        help_text=_("Select the service you want to subscribe. When you edit an existing subscription, you can not change this selection."),
        queryset=Metadata.objects.filter(
            metadata_type=MetadataEnum.SERVICE.value,
            is_active=True,
        ),
        widget=autocomplete.ModelSelect2(
            url='editor:service-autocomplete',
        ),
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
        from service.helper.enums import MetadataRelationEnum

        super().__init__(*args, **kwargs)

        if is_edit:
            # Prevent user from changing the subscribed metadata itself
            self.fields['metadata'].disabled = True
        self.fields['metadata'].queryset = self.fields['metadata'].queryset.exclude(
            related_metadata__relation_type=MetadataRelationEnum.HARVESTED_THROUGH.value,
        )

    def process_new_subscription(self):
        subscription = self.save(commit=False)
        subscription.user = self.requesting_user
        # Check if the service is already subscribed by user
        sub_already_exists = Subscription.objects.filter(
            user=self.requesting_user,
            metadata=subscription.metadata,
        ).exists()
        if sub_already_exists:
            messages.info(self.request, SUBSCRIPTION_ALREADY_EXISTS_TEMPLATE.format(subscription.metadata.title))
            del subscription
        else:
            subscription.save()
            messages.success(self.request, SUBSCRIPTION_EDITING_SUCCESSFULL)

    def process_edit_subscription(self):
        # Make sure the related metadata has not been changed
        form_subscription = self.save(commit=False)
        if form_subscription.metadata != self.instance.metadata:
            messages.error(self.request, SUBSCRIPTION_EDITING_UNSUCCESSFULL)
        else:
            form_subscription.save()
            messages.success(self.request, SUBSCRIPTION_EDITING_SUCCESSFULL)


class SubscriptionRemoveForm(MrMapConfirmForm):
    def __init__(self, instance, *args, **kwargs):
        self.instance = instance
        super().__init__(is_confirmed_label=_('Do you realy want to remove this subscription?'), *args, **kwargs)

    def process_remove_subscription(self):
        subscription_title = self.instance.metadata.title
        try:
            self.instance.delete()
            messages.success(self.request, SUBSCRIPTION_REMOVED_TEMPLATE.format(subscription_title))
        except ObjectDoesNotExist:
            messages.error(self.request, RESOURCE_NOT_FOUND_OR_NOT_OWNER)
