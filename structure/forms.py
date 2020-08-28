import datetime
from captcha.fields import CaptchaField
from django import forms
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from MrMap.forms import MrMapModelForm, MrMapForm, MrMapConfirmForm
from MrMap.messages import ORGANIZATION_IS_OTHERS_PROPERTY, \
    GROUP_IS_OTHERS_PROPERTY, PUBLISH_REQUEST_ABORTED_IS_PENDING, \
    PUBLISH_REQUEST_ABORTED_OWN_ORG, PUBLISH_REQUEST_ABORTED_ALREADY_PUBLISHER, REQUEST_ACTIVATION_TIMEOVER, \
    ORGANIZATION_SUCCESSFULLY_EDITED, PUBLISH_REQUEST_SENT, GROUP_SUCCESSFULLY_CREATED, GROUP_SUCCESSFULLY_DELETED, \
    GROUP_SUCCESSFULLY_EDITED
from MrMap.settings import MIN_PASSWORD_LENGTH, MIN_USERNAME_LENGTH
from MrMap.validators import PASSWORD_VALIDATORS, USERNAME_VALIDATORS
from structure.models import MrMapGroup, Organization, Role, PendingRequest, MrMapUser
from structure.settings import PENDING_REQUEST_TYPE_PUBLISHING, PUBLISH_REQUEST_ACTIVATION_TIME_WINDOW
from django.contrib import messages


class LoginForm(forms.Form):
    username = forms.CharField(max_length=255, label=_("Username"), label_suffix=" ")
    password = forms.CharField(max_length=255, label=_("Password"), label_suffix=" ", widget=forms.PasswordInput)
    next = forms.CharField(max_length=255, show_hidden_initial=False, widget=forms.HiddenInput(), required=False)


class GroupForm(MrMapModelForm):
    description = forms.CharField(
        label=_("Description"),
        widget=forms.Textarea(),
        required=False, )
    role = forms.ModelChoiceField(
        label=_("Role"),
        queryset=Role.objects.all(),
        empty_label=None, )

    class Meta:
        model = MrMapGroup
        fields = [
            "name",
            "description",
            "role",
            "parent_group"
        ]
        labels = {
            "parent_group": _("Parent group"),
        }
        help_text = {
        }

    def __init__(self, *args, **kwargs):
        super(GroupForm, self).__init__(*args, **kwargs)

        if 'instance' in kwargs:
            groups = self.requesting_user.get_groups()
            instance = kwargs.get('instance')
            exclusions = [instance]
            for group in groups:
                group_ = group
                while group_.parent_group is not None:
                    if group_.parent_group == instance:
                        exclusions.append(group)
                    group_ = group_.parent_group

            self.fields['parent_group'].queryset = MrMapGroup.objects.all().exclude(id__in=[o.id for o in exclusions])

    def clean(self):
        cleaned_data = super(GroupForm, self).clean()

        if self.instance.created_by_id is not None and self.instance.created_by != self.requesting_user:
            self.add_error(None, GROUP_IS_OTHERS_PROPERTY)

        parent_group = None if 'parent_group' not in cleaned_data else cleaned_data['parent_group']

        if parent_group is not None:
            if self.instance == parent_group:
                self.add_error('parent_group', "Circular configuration of parent groups detected.")
            else:
                while parent_group.parent_group is not None:
                    if self.instance == parent_group.parent_group:
                        self.add_error('parent_group', "Circular configuration of parent groups detected.")
                        break
                    else:
                        parent_group = parent_group.parent_group

        return cleaned_data

    def process_new_group(self):
        # save changes of group
        group = self.save(commit=False)
        group.created_by = self.requesting_user
        if group.role is None:
            group.role = Role.objects.get(name="_default_")
        group.save()
        group.user_set.add(self.requesting_user)
        messages.success(self.request, message=GROUP_SUCCESSFULLY_CREATED.format(group.name))

    def process_edit_group(self):
        # save changes of group
        self.instance.save()
        messages.success(self.request, message=GROUP_SUCCESSFULLY_EDITED.format(self.instance.name))


class PublisherForOrganizationForm(MrMapForm):
    action_url = ''
    organization_name = forms.CharField(
        max_length=500,
        label_suffix=" ",
        label=_("Organization"),
        disabled=True,
        help_text=_("The organization you are requesting"),
    )
    group = forms.ModelChoiceField(
        queryset=None,
        label=_("Group"),
        help_text=_("Select your group for which you want to request publisher rights"),
    )
    request_msg = forms.CharField(
        widget=forms.Textarea(),
        required=True,
        label=_("Message"),
        label_suffix=" ",
    )

    def __init__(self, organization, *args, **kwargs):
        self.organization = organization
        super(PublisherForOrganizationForm, self).__init__(*args, **kwargs)

        self.fields['group'].queryset = self.requesting_user.get_groups()
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

    def process_new_publisher_request(self):
        publish_request_obj = PendingRequest()
        publish_request_obj.type = PENDING_REQUEST_TYPE_PUBLISHING
        publish_request_obj.organization = self.organization
        publish_request_obj.message = self.cleaned_data["request_msg"]
        publish_request_obj.group = self.cleaned_data["group"]
        publish_request_obj.activation_until = timezone.now() + datetime.timedelta(
            hours=PUBLISH_REQUEST_ACTIVATION_TIME_WINDOW)
        publish_request_obj.save()
        # create pending publish request for organization!
        messages.success(self.request, message=PUBLISH_REQUEST_SENT)


class OrganizationForm(MrMapModelForm):
    description = forms.CharField(
        widget=forms.Textarea(),
        label=_('Description'),
        required=False, )
    person_name = forms.CharField(
        label=_("Contact person"),
        required=True, )

    field_order = [
        "organization_name",
        "description",
        "parent",
        "person_name",
        "email",
        "phone",
        "facsimile",
        "country",
        "state_or_province",
        "city",
        "postal_code",
        "address",
    ]

    class Meta:
        model = Organization
        fields = '__all__'
        exclude = ["created_by", "address_type", "is_auto_generated"]
        labels = {
            "organization_name": _("Organization name"),
            "description": _("Description"),
            "parent": _("Parent"),
            "facsimile": _("Facsimile"),
            "phone": _("Phone"),
            "email": _("E-Mail"),
            "city": _("City"),
            "postal_code": _("Postal code"),
            "address": _("Address"),
            "state_or_province": _("State or province"),
            "country": _("Country"),
        }

    def __init__(self, *args, **kwargs):
        super(OrganizationForm, self).__init__(*args, **kwargs)

        if 'instance' in kwargs:
            org_ids_of_groups = []
            for group in self.requesting_user.get_groups():
                org_ids_of_groups.append(group.id)

            all_orgs_of_requesting_user = Organization.objects.filter(created_by=self.requesting_user) | \
                                          Organization.objects.filter(id=self.requesting_user.organization.id) | \
                                          Organization.objects.filter(id__in=org_ids_of_groups)

            instance = kwargs.get('instance')
            exclusions = [instance]
            for org in all_orgs_of_requesting_user:
                org_ = org
                while org_.parent is not None:
                    if org_.parent == instance:
                        exclusions.append(org)
                    org_ = org_.parent

            self.fields['parent'].queryset = all_orgs_of_requesting_user.exclude(id__in=[o.id for o in exclusions])

    def clean(self):
        cleaned_data = super(OrganizationForm, self).clean()

        if self.instance.created_by is not None and self.instance.created_by != self.requesting_user:
            self.add_error(None, ORGANIZATION_IS_OTHERS_PROPERTY)

        parent = None if 'parent' not in cleaned_data else cleaned_data['parent']

        if parent is not None:
            if self.instance == parent:
                self.add_error('parent_group', "Circular configuration of parent organization detected.")
            else:
                while parent.parent is not None:
                    if self.instance == parent.parent:
                        self.add_error('parent', "Circular configuration of parent organization detected.")
                        break
                    else:
                        parent = parent.parent

        return cleaned_data

    def process_edit_org(self):
        # save changes of organization
        self.save()
        messages.success(self.request, message=ORGANIZATION_SUCCESSFULLY_EDITED.format(self.instance.organization_name))

    def process_new_org(self):
        # save changes of group
        org = self.save(commit=False)
        org.created_by = self.requesting_user
        org.is_auto_generated = False  # when the user creates an organization per form, it is not auto generated!
        org.save()
        messages.success(self.request, message=_('Organization {} successfully created.'.format(org.organization_name)))


class RemoveGroupForm(MrMapConfirmForm):

    def __init__(self, instance=None, *args, **kwargs):
        self.instance = instance
        super(RemoveGroupForm, self).__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super(RemoveGroupForm, self).clean()
        if self.instance.created_by is not None and self.instance.created_by != self.requesting_user:
            self.add_error(None, GROUP_IS_OTHERS_PROPERTY)
        return cleaned_data

    def process_remove_group(self):
        group_name = self.instance.name
        # clean subgroups from parent
        sub_groups = MrMapGroup.objects.filter(
            parent_group=self.instance
        )
        for sub in sub_groups:
            sub.parent = None
            sub.save()
        # remove group and all of the related content
        self.instance.delete()
        messages.success(self.request, message=GROUP_SUCCESSFULLY_DELETED.format(group_name))

class RemoveOrganizationForm(MrMapConfirmForm):
    def __init__(self, instance=None, *args, **kwargs):
        self.instance = instance
        super(RemoveOrganizationForm, self).__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super(RemoveOrganizationForm, self).clean()

        if self.instance.created_by != self.requesting_user:
            self.add_error(None, ORGANIZATION_IS_OTHERS_PROPERTY)

        if not cleaned_data.get('is_confirmed'):
            self.add_error('is_confirmed', _('You have to confirm the checkbox.'))

        return cleaned_data

    def process_remove_org(self):
        org_name = self.instance.organization_name
        self.instance.delete()
        messages.success(self.request, message=_('Organization {} successfully deleted.'.format(org_name)))


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

        # Username taken check
        u_name = cleaned_data.get("username", None)
        u_exists = MrMapUser.objects.filter(username=u_name).exists()
        if u_exists:
            self.add_error("username", forms.ValidationError(_("Username is already taken. Try another.")))

        # Password check
        password = cleaned_data.get("password")
        password_check = cleaned_data.get("password_check")

        if password != password_check:
            self.add_error("password_check", forms.ValidationError(_("Passwords do not match.")))

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
