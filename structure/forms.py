from captcha.fields import CaptchaField
from django import forms
from django.forms import ModelForm
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from MapSkinner.messages import ORGANIZATION_IS_OTHERS_PROPERTY, \
    GROUP_IS_OTHERS_PROPERTY, PUBLISH_REQUEST_ABORTED_IS_PENDING, \
    PUBLISH_REQUEST_ABORTED_OWN_ORG, PUBLISH_REQUEST_ABORTED_ALREADY_PUBLISHER, REQUEST_ACTIVATION_TIMEOVER, \
    PUBLISH_PERMISSION_REMOVING_DENIED
from MapSkinner.settings import MIN_PASSWORD_LENGTH, MIN_USERNAME_LENGTH
from MapSkinner.validators import PASSWORD_VALIDATORS, USERNAME_VALIDATORS
from structure.models import MrMapGroup, Organization, Role, PendingRequest
from structure.settings import PENDING_REQUEST_TYPE_PUBLISHING


class LoginForm(forms.Form):
    username = forms.CharField(max_length=255, label=_("Username"), label_suffix=" ")
    password = forms.CharField(max_length=255, label=_("Password"), label_suffix=" ", widget=forms.PasswordInput)
    next = forms.CharField(max_length=255, show_hidden_initial=False, widget=forms.HiddenInput(), required=False)


class GroupForm(ModelForm):
    # this action_url must fill after this object is created,
    # cause the action_url containing the id of the group, which is not present on building time;
    # maybe we could fill it by the constructor
    action_url = ''

    description = forms.CharField(
        widget=forms.Textarea(),
        required=False,
    )
    role = forms.ModelChoiceField(queryset=Role.objects.all(), empty_label=None)

    class Meta:
        model = MrMapGroup
        fields = [
            "name",
            "description",
            "role",
            "parent_group"
        ]

    def __init__(self, *args, **kwargs):
        self.requesting_user = None if 'requesting_user' not in kwargs else kwargs.pop('requesting_user')
        self.is_edit = False if 'is_edit' not in kwargs else kwargs.pop('is_edit')
        super(GroupForm, self).__init__(*args, **kwargs)

        if 'instance' in kwargs:
            self.fields['parent_group'].queryset = MrMapGroup.objects.all().exclude(id=kwargs.get('instance').id)

        if self.is_edit:
            self.action_url = reverse('structure:edit-group', args=[self.instance.id])
        else:
            self.action_url = reverse('structure:new-group')

    def clean(self):
        cleaned_data = super(GroupForm, self).clean()

        if self.instance.created_by_id is not None and self.instance.created_by != self.requesting_user:
            self.add_error(None, GROUP_IS_OTHERS_PROPERTY)

        return cleaned_data


class PublisherForOrganizationForm(forms.Form):
    action_url = ''
    organization_name = forms.CharField(max_length=500, label_suffix=" ", label=_("Organization"), disabled=True)
    group = forms.ModelChoiceField(queryset=None)
    request_msg = forms.CharField(
        widget=forms.Textarea(),
        required=True,
        label=_("Message"),
        label_suffix=" ",
    )

    def __init__(self, *args, **kwargs):
        self.requesting_user = None if 'requesting_user' not in kwargs else kwargs.pop('requesting_user')
        self.organization = None if 'organization' not in kwargs else kwargs.pop('organization')
        super(PublisherForOrganizationForm, self).__init__(*args, **kwargs)

        if self.requesting_user is not None:
            self.fields['group'].queryset = self.requesting_user.get_groups()

        if self.organization is not None:
            self.fields["organization_name"].initial = self.organization.organization_name

    def clean(self):
        cleaned_data = super(PublisherForOrganizationForm, self).clean()

        group = MrMapGroup.objects.get(id=cleaned_data["group"].id)

        # check if user is already a publisher using this group or a request already has been created
        pub_request = PendingRequest.objects.filter(type=PENDING_REQUEST_TYPE_PUBLISHING, organization=self.organization, group=group)
        if self.organization in group.publish_for_organizations.all() or pub_request.count() > 0 or self.organization == group.organization:
            if pub_request.count() > 0:
                self.add_error(None, PUBLISH_REQUEST_ABORTED_IS_PENDING)
            elif self.organization == group.organization:
                self.add_error("group", PUBLISH_REQUEST_ABORTED_OWN_ORG)
            else:
                self.add_error(None, PUBLISH_REQUEST_ABORTED_ALREADY_PUBLISHER)

        return cleaned_data


class OrganizationForm(ModelForm):
    # this action_url must fill after this object is created,
    # cause the action_url containing the id of the group, which is not present on building time;
    # maybe we could fill it by the constructor
    action_url = ''

    description = forms.CharField(
        widget=forms.Textarea(),
        required=False,
    )
    person_name = forms.CharField(label=_("Contact person"), required=True)

    field_order = ["organization_name", "description", "parent"]

    class Meta:
        model = Organization
        fields = '__all__'
        exclude = ["created_by", "address_type", "is_auto_generated"]

    def __init__(self, *args, **kwargs):
        self.requesting_user = None if 'requesting_user' not in kwargs else kwargs.pop('requesting_user')
        self.is_edit = False if 'is_edit' not in kwargs else kwargs.pop('is_edit')
        super(OrganizationForm, self).__init__(*args, **kwargs)

        if 'instance' in kwargs:
            self.fields['parent'].queryset = Organization.objects.all().exclude(id=kwargs.get('instance').id)

        if self.is_edit:
            self.action_url = reverse('structure:edit-organization', args=[self.instance.id])
        else:
            self.action_url = reverse('structure:new-organization')

    def clean(self):
        cleaned_data = super(OrganizationForm, self).clean()

        if self.instance.created_by is not None and self.instance.created_by != self.requesting_user:
            self.add_error(None, ORGANIZATION_IS_OTHERS_PROPERTY)

        return cleaned_data


class RemoveGroupForm(forms.Form):
    action_url = ''
    is_confirmed = forms.BooleanField(label=_('Do you really want to remove this group?'))

    def __init__(self, *args, **kwargs):
        self.requesting_user = None if 'requesting_user' not in kwargs else kwargs.pop('requesting_user')
        self.instance = None if 'instance' not in kwargs else kwargs.pop('instance')
        super(RemoveGroupForm, self).__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super(RemoveGroupForm, self).clean()

        if self.instance.created_by is not None and self.instance.created_by != self.requesting_user:
            self.add_error(None, GROUP_IS_OTHERS_PROPERTY)

        return cleaned_data


class RemoveOrganizationForm(forms.Form):
    action_url = ''
    is_confirmed = forms.BooleanField(label=_('Do you really want to remove this organization?'))

    def __init__(self, *args, **kwargs):
        self.requesting_user = None if 'requesting_user' not in kwargs else kwargs.pop('requesting_user')
        self.instance = None if 'instance' not in kwargs else kwargs.pop('instance')
        super(RemoveOrganizationForm, self).__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super(RemoveOrganizationForm, self).clean()

        if self.instance.created_by != self.requesting_user:
            self.add_error(None, ORGANIZATION_IS_OTHERS_PROPERTY)

        if not cleaned_data.get('is_confirmed'):
            self.add_error('is_confirmed', _('You have to confirm the checkbox.'))

        return cleaned_data


class RegistrationForm(forms.Form):
    username = forms.CharField(
        min_length=MIN_USERNAME_LENGTH,
        max_length=255,
        validators=USERNAME_VALIDATORS,
        label=_("Username"),
        label_suffix=" ",
        required=True
    )
    password = forms.CharField(
        min_length=MIN_PASSWORD_LENGTH,
        max_length=255,
        label=_("Password"),
        label_suffix=" ",
        widget=forms.PasswordInput,
        required=True,
        validators=PASSWORD_VALIDATORS
    )

    password_check = forms.CharField(
        max_length=255,
        label=_("Password again"),
        label_suffix=" ",
        widget=forms.PasswordInput,
        required=True
    )

    first_name = forms.CharField(max_length=200, label=_("First name"), label_suffix=" ", required=True)
    last_name = forms.CharField(max_length=200, label=_("Last name"), label_suffix=" ", required=True)
    email = forms.EmailField(max_length=100, label=_("E-mail address"), label_suffix=" ", required=True)
    address = forms.CharField(max_length=100, label=_("Address"), label_suffix=" ", required=False)
    postal_code = forms.CharField(max_length=100, label=_("Postal code"), label_suffix=" ", required=False)
    city = forms.CharField(max_length=100, label=_("City"), label_suffix=" ", required=False)
    phone = forms.CharField(max_length=100, label=_("Phone"), label_suffix=" ", required=True)
    facsimile = forms.CharField(max_length=100, label=_("Facsimile"), label_suffix=" ", required=False)
    newsletter = forms.BooleanField(label=_("I want to sign up for the newsletter"), required=False, initial=True)
    survey = forms.BooleanField(label=_("I want to participate in surveys"), required=False, initial=True)
    dsgvo = forms.BooleanField(
        initial=False,
        label=_("I understand and accept that my data will be automatically processed and securely stored, as it is stated in the general data protection regulation (GDPR)."),
        required=True
    )
    captcha = CaptchaField(label=_("I'm not a robot"), required=True)

    def clean(self):
        cleaned_data = super(RegistrationForm, self).clean()
        password = cleaned_data.get("password")
        password_check = cleaned_data.get("password_check")

        if password != password_check:
            self.add_error("password_check", forms.ValidationError(_("Password and confirmed password does not match")))

        return cleaned_data


class AcceptDenyPublishRequestForm(forms.Form):
    is_accepted = forms.BooleanField(required=False)

    def __init__(self, *args, **kwargs):
        self.pub_request = None if 'pub_request' not in kwargs else kwargs.pop('pub_request')
        super(AcceptDenyPublishRequestForm, self).__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super(AcceptDenyPublishRequestForm, self).clean()

        now = timezone.now()

        if self.pub_request.activation_until <= now:
            self.add_error(None, REQUEST_ACTIVATION_TIMEOVER)
            self.pub_request.delete()

        return cleaned_data


class RemovePublisher(forms.Form):
    is_accepted = forms.BooleanField(required=False)

    def __init__(self, *args, **kwargs):
        self.user = None if 'user' not in kwargs else kwargs.pop('user')
        self.organization = None if 'organization' not in kwargs else kwargs.pop('organization')
        self.group = None if 'group' not in kwargs else kwargs.pop('group')
        super(RemovePublisher, self).__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super(RemovePublisher, self).clean()

        if self.group not in self.user.get_groups() and self.user.organization != self.organization:
            self.add_error(None, PUBLISH_PERMISSION_REMOVING_DENIED)

        return cleaned_data
