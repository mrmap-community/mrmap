import django_tables2 as tables
from users.tables.template_codes import PUBLISHES_REQUEST_BUTTON, REMOVE_PUBLISHER_BUTTON
from django.utils.translation import gettext_lazy as _
from acls.models.acls import AccessControlList
from extras.tables.columns import DefaultActionButtonsColumn
from extras.tables.template_code import VALUE_ABSOLUTE_LINK, RECORD_ABSOLUTE_LINK
from users.models.groups import Organization, PublishRequest
from extras.tables.tables import SecuredTable


class PublishesRequestTable(SecuredTable):
    perm_checker = None
    from_organization = tables.TemplateColumn(
        template_code=VALUE_ABSOLUTE_LINK,
    )
    to_organization = tables.TemplateColumn(
        template_code=VALUE_ABSOLUTE_LINK,
    )
    actions = tables.TemplateColumn(template_code=PUBLISHES_REQUEST_BUTTON,
                                    verbose_name=_('Actions'),
                                    empty_values=[],
                                    orderable=False,
                                    attrs={"td": {"style": "white-space:nowrap;"}},
                                    extra_context={'perm_checker': perm_checker})

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


class OrganizationPublishersTable(SecuredTable):
    perm_checker = None
    name = tables.TemplateColumn(
        template_code=VALUE_ABSOLUTE_LINK
    )

    actions = tables.TemplateColumn(template_code=REMOVE_PUBLISHER_BUTTON,
                                    verbose_name=_('Actions'),
                                    empty_values=[],
                                    orderable=False,
                                    attrs={"td": {"style": "white-space:nowrap;"}},
                                    extra_context={'perm_checker': perm_checker})

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
