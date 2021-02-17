import os

from captcha.fields import CaptchaField
from dal import autocomplete
from django import forms
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError, ObjectDoesNotExist, ImproperlyConfigured
from django.db import transaction
from django.db.models import Q
from django.forms import ModelForm, HiddenInput, MultipleHiddenInput
from django.http import Http404
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


class GroupForm(ModelForm):
    user_set = forms.ModelMultipleChoiceField(queryset=MrMapUser.objects.all(),
                                              label=_('Members'),
                                              widget=autocomplete.ModelSelect2Multiple(url='editor:users'))

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
            "created_by",
        ]
        widgets = {
            "description": forms.Textarea(),
            "created_by": forms.HiddenInput()
        }

    def __init__(self, request, *args, **kwargs):
        self.request = request

        super(GroupForm, self).__init__(*args, **kwargs)

        if kwargs.get('instance', None):
            groups = self.request.user.get_groups()

            instance = kwargs.get('instance')
            exclusions = [instance]
            for group in groups:
                group_ = group
                while group_.parent_group is not None:
                    if group_.parent_group == instance:
                        exclusions.append(group)
                    group_ = group_.parent_group

            self.fields['parent_group'].queryset = MrMapGroup.objects.all().exclude(id__in=[o.id for o in exclusions])
            self.fields['user_set'].initial = instance.user_set.all()
        else:
            self.fields['created_by'].initial = self.request.user

    def clean(self):
        cleaned_data = super(GroupForm, self).clean()

        if self.instance.created_by_id is not None and self.instance.created_by != self.request.user:
            self.add_error(None, GROUP_IS_OTHERS_PROPERTY)

        parent_group = None if 'parent_group' not in cleaned_data else cleaned_data['parent_group']

        if parent_group is not None:
            if self.instance == parent_group:
                self.add_error('parent_group', _("Circular configuration of parent groups detected."))
            else:
                while parent_group.parent_group is not None:
                    if self.instance == parent_group.parent_group:
                        self.add_error('parent_group', _("Circular configuration of parent groups detected."))
                        break
                    else:
                        parent_group = parent_group.parent_group

        return cleaned_data

    def save(self, commit=True):
        self.instance.save()
        self.instance.user_set.clear()
        self.instance.user_set.add(*self.cleaned_data['user_set'])
        return self.instance


class RemoveUserFromGroupForm(ModelForm):
    user_set = forms.ModelMultipleChoiceField(queryset=MrMapUser.objects.all(),
                                              label=_('Members'),
                                              widget=MultipleHiddenInput())

    class Meta:
        model = MrMapGroup
        fields = ()

    def __init__(self, user, *args, **kwargs):
        super(RemoveUserFromGroupForm, self).__init__(*args, **kwargs)
        instance = kwargs.get('instance')
        if instance:
            self.fields['user_set'].initial = instance.user_set.exclude(username=user.username)
        else:
            raise ImproperlyConfigured("RemoveUserFromGroupForm without instance kw isn't possible")

    def save(self, commit=True):
        self.instance.user_set.clear()
        self.instance.user_set.add(*self.cleaned_data['user_set'])
        return self.instance


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


class OrganizationForm(forms.ModelForm):
    person_name = forms.CharField(
        label=_("Contact person"),
        required=True, )

    publishers = forms.ModelMultipleChoiceField(queryset=MrMapGroup.objects.all(),
                                                label=_('Publishers'),
                                                widget=autocomplete.ModelSelect2Multiple(url='editor:groups'),
                                                required=False)

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

    def __init__(self, request, *args, **kwargs):
        self.request = request
        super(OrganizationForm, self).__init__(*args, **kwargs)

        instance = kwargs.get('instance')
        if instance:
            org_ids_of_groups = []
            for group in self.request.user.get_groups():
                org_ids_of_groups.append(group.id)

            all_orgs_of_requesting_user = Organization.objects.filter(Q(created_by=self.request.user) |
                                                                      Q(id=self.request.user.organization.id) |
                                                                      Q(id__in=org_ids_of_groups))
            # filter parent queryset to avoid of configuring circular inheritance settings
            exclusions = [instance]
            for org in all_orgs_of_requesting_user:
                org_ = org
                while org_.parent is not None:
                    if org_.parent == instance:
                        exclusions.append(org)
                    org_ = org_.parent
            self.fields['parent'].queryset = all_orgs_of_requesting_user.exclude(id__in=[o.id for o in exclusions])
            self.fields['publishers'].initial = instance.publishers.all()
            self.fields.pop('create_group')

    def clean(self):
        cleaned_data = super(OrganizationForm, self).clean()
        self.instance.check_circular_configuration(self.instance)
        return cleaned_data

    @transaction.atomic
    def save(self, commit=True):
        # save changes of group
        self.instance.created_by = self.request.user
        self.instance.is_auto_generated = False  # when the user creates an organization per form, it is not auto generated!
        self.instance = super().save(commit)
        self.instance.publishers.clear()
        self.instance.publishers.add(*self.cleaned_data['publishers'])

        if self.cleaned_data.get('created_group'):
            org_group = MrMapGroup.objects.create(
                name=_("{} group").format(self.instance.organization_name),
                organization=self.instance,
                created_by=self.request.user,
            )
            org_group.user_set.add(self.request.user)
            org_group.save()
            messages.success(self.request, message=_('Group {} successfully created.'.format(org_group.name)))
        return self.instance


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


class RegistrationForm(forms.ModelForm):

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

    dsgvo = forms.BooleanField(
        initial=False,
        label=_("I understand and accept that my data will be automatically processed and securely stored, as it is stated in the general data protection regulation (GDPR)."),
        required=True
    )
    captcha = CaptchaField(label=_("I'm not a robot"), required=True)

    class Meta:
        model = MrMapUser
        fields = ('username',
                  'password',
                  'password_check',
                  'first_name',
                  'last_name',
                  'email',
                  'confirmed_newsletter',
                  'confirmed_survey',
                  'dsgvo',
                  'captcha')

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

    def save(self, commit=True):
        self.instance.salt = str(os.urandom(25).hex())
        self.instance.password = make_password(self.instance.password, salt=self.instance.salt)
        self.instance.person_name = self.instance.first_name + " " + self.instance.last_name
        self.instance.is_active = False
        return super().save(commit=commit)

        # todo: move this to a signal
        """
        # Add user to Public group
        public_group = MrMapGroup.objects.get(
            is_public_group=True
        )
        public_group.user_set.add(self.instance)

        # create user_activation object to improve checking against activation link
        self.instance.create_activation()"""
