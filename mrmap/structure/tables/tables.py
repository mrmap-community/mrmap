import django_tables2 as tables
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from acl.models.acl import AccessControlList
from main.tables.columns import DefaultActionButtonsColumn
from main.tables.template_code import VALUE_ABSOLUTE_LINK, RECORD_ABSOLUTE_LINK
from main.template_codes.template_codes import PERMISSIONS
from structure.models import Organization, PublishRequest
from structure.tables.columns import PublishesRequestButtonsColumn, RemovePublisherButtonColumn



class PublishesRequestTable(tables.Table):
    from_organization = tables.TemplateColumn(
        template_code=VALUE_ABSOLUTE_LINK,
    )
    to_organization = tables.TemplateColumn(
        template_code=VALUE_ABSOLUTE_LINK,
    )
    actions = PublishesRequestButtonsColumn()

    class Meta:
        model = PublishRequest
        fields = ('from_organization', 'to_organization', 'message', 'actions')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'publishers-for-table'


class OrganizationDetailTable(tables.Table):
    class Meta:
        model = Organization
        fields = ('name',
                  'parent',
                  'person_name',
                  'email',
                  'phone',
                  'facsimile',
                  'city',
                  'postal_code',
                  'address',
                  'state_or_province',
                  'country')
        template_name = "skeletons/django_tables2_vertical_table.html"
        prefix = 'organization-detail-table'
        orderable = False


class OrganizationTable(tables.Table):
    name = tables.TemplateColumn(template_code=RECORD_ABSOLUTE_LINK)
    actions = DefaultActionButtonsColumn(model=Organization)

    class Meta:
        model = Organization
        fields = ('name', 'description')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'organizations-table'


class OrganizationPublishersTable(tables.Table):
    name = tables.TemplateColumn(
        template_code=VALUE_ABSOLUTE_LINK
    )

    actions = RemovePublisherButtonColumn()

    class Meta:
        model = Organization
        fields = ('name', )
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'publishers-table'


class OrganizationAccessControlListTable(tables.Table):
    class Meta:
        model = AccessControlList
        fields = ('name', 'user_set')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'publishers-table'

    def render_user_set(self, value):
        return value.count()


class MrMapUserTable(tables.Table):
    class Meta:
        model = get_user_model()
        fields = ('username', 'organization', 'groups', 'is_superuser')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
