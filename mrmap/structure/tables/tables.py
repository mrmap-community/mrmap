import django_tables2 as tables
from django.contrib.auth import get_user_model
from django.utils.html import format_html
from django_bootstrap_swt.components import Link, Tag, Badge, LinkButton
from django_bootstrap_swt.enums import ButtonColorEnum, TooltipPlacementEnum
from django_bootstrap_swt.utils import RenderHelper
from django_tables2.utils import Accessor

from MrMap.icons import IconEnum
from MrMap.tables import ActionTableMixin
from MrMap.utils import get_ok_nok_icon, signal_last
from django.utils.translation import gettext_lazy as _

from guardian_roles.models.acl import AccessControlList
from main.tables.columns import DefaultActionButtonsColumn
from main.tables.template_code import VALUE_ABSOLUTE_LINK, RECORD_ABSOLUTE_LINK
from main.template_codes.template_codes import PERMISSIONS
from structure.models import Organization, PublishRequest
from structure.tables.columns import PublishesRequestButtonsColumn, RemovePublisherButtonColumn, EditRoleButtonColumn


class PendingRequestTable(ActionTableMixin, tables.Table):
    def before_render(self, request):
        self.render_helper = RenderHelper(user_permissions=list(filter(None, request.user.get_all_permissions())))

    def render_actions(self, record):
        ok_icon = Tag(tag='i', attrs={"class": [IconEnum.OK.value]}).render()
        st_ok_text = Tag(tag='div', attrs={"class": ['d-lg-none']}, content=ok_icon).render()
        gt_ok_text = Tag(tag='div', attrs={"class": ['d-none', 'd-lg-block']},
                         content=ok_icon + _(' accept').__str__()).render()
        nok_icon = Tag(tag='i', attrs={"class": [IconEnum.NOK.value]}).render()
        st_nok_text = Tag(tag='div', attrs={"class": ['d-lg-none']}, content=nok_icon).render()
        gt_nok_text = Tag(tag='div', attrs={"class": ['d-none', 'd-lg-block']},
                          content=nok_icon + _(' deny').__str__()).render()

        actions = [
            LinkButton(url=f"{record.accept_request_uri}?is_accepted=True",
                       content=st_ok_text+gt_ok_text,
                       color=ButtonColorEnum.SUCCESS),
            LinkButton(url=f"{record.accept_request_uri}",
                       content=st_nok_text + gt_nok_text,
                       color=ButtonColorEnum.DANGER)

        ]
        self.render_helper.update_attrs = {"class": ["mr-1"]}
        rendered_items = format_html(self.render_helper.render_list_coherent(items=actions))
        self.render_helper.update_attrs = None
        return rendered_items


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
        fields = ('organization_name',
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
    organization_name = tables.TemplateColumn(template_code=RECORD_ABSOLUTE_LINK)
    actions = DefaultActionButtonsColumn(model=Organization)

    class Meta:
        model = Organization
        fields = ('organization_name', 'description')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'organizations-table'


class OrganizationPublishersTable(tables.Table):
    organization_name = tables.TemplateColumn(
        template_code=VALUE_ABSOLUTE_LINK
    )

    actions = RemovePublisherButtonColumn()

    class Meta:
        model = Organization
        fields = ('organization_name', )
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


class MrMapUserTable(ActionTableMixin, tables.Table):
    class Meta:
        model = get_user_model()
        fields = ('username', 'organization', 'groups', 'is_superuser')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"

    def before_render(self, request):
        self.render_helper = RenderHelper(user_permissions=list(filter(None, request.user.get_all_permissions())))

    def render_actions(self, record):
        remove_icon = Tag(tag='i', attrs={"class": [IconEnum.ADD.value]}).render()
        st_invite_text = Tag(tag='div', attrs={"class": ['d-lg-none']}, content=remove_icon).render()
        gt_invite_text = Tag(tag='div', attrs={"class": ['d-none', 'd-lg-block']},
                             content=remove_icon + _(' Invite').__str__()).render()
        btns = [
            """LinkButton(url=f"{record.invite_to_group_url}",
                       content=st_invite_text + gt_invite_text,
                       color=ButtonColorEnum.SUCCESS,
                       tooltip=_(f"Invite <strong>{record}</strong>"),
                       tooltip_placement=TooltipPlacementEnum.LEFT)"""
        ]
        return []
        return format_html(self.render_helper.render_list_coherent(items=btns))
