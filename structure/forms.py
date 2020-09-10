from captcha.fields import CaptchaField
from django import forms
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from MrMap import utils
from MrMap.forms import MrMapModelForm, MrMapForm, MrMapConfirmForm
from MrMap.management.commands.setup_settings import DEFAULT_ROLE_NAME
from MrMap.messages import ORGANIZATION_IS_OTHERS_PROPERTY, \
    GROUP_IS_OTHERS_PROPERTY, PUBLISH_REQUEST_ABORTED_IS_PENDING, \
    PUBLISH_REQUEST_ABORTED_OWN_ORG, PUBLISH_REQUEST_ABORTED_ALREADY_PUBLISHER, REQUEST_ACTIVATION_TIMEOVER, \
    ORGANIZATION_SUCCESSFULLY_EDITED, PUBLISH_REQUEST_SENT, GROUP_SUCCESSFULLY_CREATED, GROUP_SUCCESSFULLY_DELETED, \
    GROUP_SUCCESSFULLY_EDITED, GROUP_INVITATION_EXISTS, GROUP_INVITATION_CREATED, PUBLISH_REQUEST_ACCEPTED, \
    PUBLISH_REQUEST_DENIED, PUBLISH_PERMISSION_REMOVED
from MrMap.settings import MIN_PASSWORD_LENGTH, MIN_USERNAME_LENGTH
from MrMap.validators import PASSWORD_VALIDATORS, USERNAME_VALIDATORS
from structure.models import MrMapGroup, Organization, Role, MrMapUser, PublishRequest, GroupInvitationRequest
from structure.settings import PUBLISH_REQUEST_ACTIVATION_TIME_WINDOW, GROUP_INVITATION_REQUEST_ACTIVATION_TIME_WINDOW
from django.contrib import messages

from users.helper import user_helper
from users.helper.user_helper import create_group_activity


class LoginForm(forms.Form):
    username = forms.CharField(max_length=255, label=_("Username"), label_suffix=" ")
    password = forms.CharField(max_length=255, label=_("Password"), label_suffix=" ", widget=forms.PasswordInput)
    next = forms.CharField(max_length=255, show_hidden_initial=False, widget=forms.HiddenInput(), required=False)


class GroupForm(MrMapModelForm):
    description = forms.CharField(
        label=_("Description"),
        widget=forms.Textarea(),
        required=False, )
    parent_group = forms.ModelChoiceField(
        label=_("Parent group"),
        queryset=MrMapGroup.objects.filter(
            is_permission_group=False
        ),
        empty_label='---------',
        required=False,
    )

    class Meta:
        model = MrMapGroup
        fields = [
            "name",
            "description",
            "parent_group",
            "organization",
        ]
        labels = {
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
            group.role = Role.objects.get_or_create(name=DEFAULT_ROLE_NAME)[0]
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
        queryset=MrMapGroup.objects.none(),
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

        groups = self.requesting_user.get_groups()
        self.fields['group'].queryset = groups.filter(is_permission_group=False)
        self.fields["organization_name"].initial = self.organization.organization_name

    def clean(self):
        cleaned_data = super(PublisherForOrganizationForm, self).clean()

        group = MrMapGroup.objects.get(id=cleaned_data["group"].id)

        # check if user is already a publisher using this group or a request already has been created
        pub_request = PublishRequest.objects.filter(organization=self.organization, group=group)
        if self.organization in group.publish_for_organizations.all() or pub_request.count() > 0 or self.organization == group.organization:
            if pub_request.count() > 0:
                self.add_error(None, PUBLISH_REQUEST_ABORTED_IS_PENDING)
            elif self.organization == group.organization:
                self.add_error("group", PUBLISH_REQUEST_ABORTED_OWN_ORG)
            else:
                self.add_error(None, PUBLISH_REQUEST_ABORTED_ALREADY_PUBLISHER)

        return cleaned_data

    def process_new_publisher_request(self):
        user = user_helper.get_user(self.request)
        publish_request_obj = PublishRequest()
        publish_request_obj.organization = self.organization
        publish_request_obj.message = self.cleaned_data["request_msg"]
        publish_request_obj.group = self.cleaned_data["group"]
        publish_request_obj.activation_until = timezone.now() + timezone.timedelta(
            hours=PUBLISH_REQUEST_ACTIVATION_TIME_WINDOW)
        publish_request_obj.created_by = user
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
    create_group = forms.BooleanField(
        widget=forms.CheckboxInput(),
        label=_("Create group"),
        help_text=_("If set, a group will be automatically created for this organization. Groups are needed for e.g. registration of services."),
        required=False,
    )

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

    @transaction.atomic
    def process_new_org(self):
        # save changes of group
        org = self.save(commit=False)
        org.created_by = self.requesting_user
        org.is_auto_generated = False  # when the user creates an organization per form, it is not auto generated!
        org.save()
        messages.success(self.request, message=_('Organization {} successfully created.'.format(org.organization_name)))

        create_group = self.cleaned_data.get('create_group', False)
        if create_group:
            org_group = MrMapGroup.objects.create(
                name=_("{} group").format(org.organization_name),
                organization=org,
                created_by=self.requesting_user,
            )
            org_group.user_set.add(self.requesting_user)
            org_group.save()
            messages.success(self.request, message=_('Group {} successfully created.'.format(org_group.name)))


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


class LeaveGroupForm(MrMapConfirmForm):
    def __init__(self, instance=None, *args, **kwargs):
        self.instance = instance
        super().__init__(*args, **kwargs)

    def process_leave_group(self):
        if self.instance.is_public_group:
            messages.error(self.request, _("You can't leave this group."))
        else:
            user = user_helper.get_user(self.request)
            self.instance.user_set.remove(user)
            messages.success(
                self.request,
                _("You left group {}").format(self.instance.name)
            )


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


class RemovePublisherForm(MrMapConfirmForm):

    def __init__(self, *args, **kwargs):
        self.user = None if 'user' not in kwargs else kwargs.pop('user')
        self.organization = None if 'organization' not in kwargs else kwargs.pop('organization')
        self.group = None if 'group' not in kwargs else kwargs.pop('group')
        super().__init__(*args, **kwargs)

    def clean(self):
        """

        Checks whether only member of the organization or member of the publishing group are valid users!

        Returns:

        """
        user_groups = self.user.get_groups()
        org = self.organization
        publishers = org.can_publish_for.all()
        user_is_publisher = (publishers & user_groups).exists()
        user_is_org_member = self.user.organization == org
        if not user_is_publisher and not user_is_org_member:
            raise ValidationError

    def process_remove_publisher(self):
        self.group.publish_for_organizations.remove(self.organization)
        create_group_activity(
            group=self.group,
            user=self.user,
            msg=_("Publisher changed"),
            metadata_title=_("Group '{}' has been removed as publisher for '{}'.").format(self.group, self.organization),
        )
        messages.success(self.request, message=PUBLISH_PERMISSION_REMOVED.format(self.group.name, self.organization.organization_name))


class GroupInvitationForm(MrMapForm):
    invited_user = forms.ModelChoiceField(
        label=_("User"),
        queryset=MrMapGroup.objects.none(),
        to_field_name='id',
        disabled=True,
    )
    to_group = forms.ModelChoiceField(
        label=_("Invite to group"),
        widget=forms.Select(),
        queryset=MrMapGroup.objects.none(),
        to_field_name='id',
        initial=1,
    )
    msg = forms.CharField(
        label=_('Message'),
        required=False,
        widget=forms.Textarea()
    )

    def __init__(self, *args, **kwargs):
        invited_user = None if 'invited_user' not in kwargs else kwargs.pop('invited_user')
        super().__init__(*args, **kwargs)
        requesting_user = user_helper.get_user(self.request)
        user_groups = requesting_user.get_groups().exclude(
            is_public_group=True
        )
        self.fields["invited_user"].queryset = MrMapUser.objects.filter(id=invited_user.id)
        self.fields["invited_user"].initial = invited_user
        self.fields["to_group"].queryset = user_groups
        self.fields["to_group"].initial = user_groups.first()

    def process_invitation_group(self):
        """ Processes the invitation

        Returns:

        """
        invited_user = self.cleaned_data.get("invited_user", None)
        to_group = self.cleaned_data.get("to_group", None)
        msg = self.cleaned_data.get("msg", None)
        perf_user = user_helper.get_user(self.request)

        try:
            group_invitation_obj = GroupInvitationRequest.objects.get(
                invited_user=invited_user,
                to_group=to_group,
                created_by=perf_user,
            )
            messages.info(
                request=self.request,
                message=GROUP_INVITATION_EXISTS.format(invited_user, group_invitation_obj.activation_until)
            )
        except ObjectDoesNotExist:
            group_invitation_obj = GroupInvitationRequest.objects.create(
                invited_user=invited_user,
                to_group=to_group,
                created_by=perf_user,
                message=msg,
                activation_until=timezone.now() + timezone.timedelta(
                    hours=GROUP_INVITATION_REQUEST_ACTIVATION_TIME_WINDOW
                )
            )
            messages.success(
                request=self.request,
                message=GROUP_INVITATION_CREATED.format(invited_user, to_group)
            )


class GroupInvitationConfirmForm(MrMapForm):
    msg = forms.CharField(
        label=_("Sender's message"),
        widget=forms.Textarea(),
        disabled=True,
        required=False,
    )
    accept = forms.ChoiceField(
        widget=forms.RadioSelect(
            attrs={
                "style": "display:inline"
            }
        ),
        label=_("Accept request"),
        choices=(
            (True, _("Accept")),
            (False, _("Decline")),
        )
    )

    def __init__(self, *args, **kwargs):
        self.invitation_request = None if "invitation" not in kwargs else kwargs.pop("invitation")
        super().__init__(*args, **kwargs)
        self.fields["msg"].initial = self.invitation_request.message

    def clean(self):
        cleaned_data = super().clean()

        now = timezone.now()

        if self.invitation_request.activation_until <= now:
            self.add_error(None, REQUEST_ACTIVATION_TIMEOVER)
            self.invitation_request.delete()

        return cleaned_data

    def process_invitation_group(self):
        accepted = utils.resolve_boolean_attribute_val(self.cleaned_data.get("accept", False))
        group = self.invitation_request.to_group
        user = self.invitation_request.invited_user
        if accepted:
            group.user_set.add(user)
            messages.success(
                self.request,
                _("You are now member of {}").format(group.name),
            )
        else:
            messages.info(
                self.request,
                _("You declined the invitation to {}").format(group.name),
            )
        self.invitation_request.delete()


class PublishRequestConfirmForm(MrMapForm):
    msg = forms.CharField(
        label=_("Sender's message"),
        widget=forms.Textarea(),
        disabled=True,
        required=False,
    )
    accept = forms.ChoiceField(
        widget=forms.RadioSelect(
            attrs={
                "style": "display:inline"
            }
        ),
        label=_("Accept request"),
        choices=(
            (True, _("Accept")),
            (False, _("Decline")),
        )
    )

    def __init__(self, *args, **kwargs):
        self.publish_request = None if "publish_request" not in kwargs else kwargs.pop("publish_request")
        super().__init__(*args, **kwargs)
        self.fields["msg"].initial = self.publish_request.message

    def process_publish_request(self):
        accepted = utils.resolve_boolean_attribute_val(self.cleaned_data.get("accept", False))

        group = self.publish_request.group
        if accepted:
            # add organization to group_publisher
            group.publish_for_organizations.add(self.publish_request.organization)
            create_group_activity(
                group=group,
                user=self.requesting_user,
                msg=_("Publisher changed"),
                metadata_title=_("Group '{}' has been accepted as publisher for '{}'".format(
                    group,
                    self.publish_request.organization)
                ),
            )
            messages.success(self.request, PUBLISH_REQUEST_ACCEPTED.format(group.name))
        else:

            create_group_activity(
                group=self.pub_request.group,
                user=self.requesting_user,
                msg=_("Publisher changed"),
                metadata_title=_("Group '{}' has been rejected as publisher for '{}'".format(
                    group,
                    self.publish_request.organization)
                ),
            )
            messages.info(self.request, PUBLISH_REQUEST_DENIED.format(group.name))
        self.publish_request.delete()


