import django_tables2 as tables
from django.contrib.auth import get_user_model
from django.utils.html import format_html
from django_bootstrap_swt.components import Link, Tag, Badge, LinkButton
from django_bootstrap_swt.enums import ButtonColorEnum, TooltipPlacementEnum
from django_bootstrap_swt.utils import RenderHelper
from MrMap.icons import IconEnum
from MrMap.tables import ActionTableMixin
from MrMap.utils import get_ok_nok_icon, signal_last
from django.utils.translation import gettext_lazy as _
from structure.models import Organization, PublishRequest


class PublishesForTable(tables.Table):
    class Meta:
        model = Organization
        fields = ('organization_name', )
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'publishers-for-table'

    def render_organization_name(self, record, value):
        return Link(url=record.detail_view_uri, content=value).render(safe=True)


class PendingRequestTable(ActionTableMixin, tables.Table):
    def before_render(self, request):
        self.render_helper = RenderHelper(user_permissions=list(filter(None, request.user.get_all_permissions())))

    def render_organization(self, value):
        return Link(url=value.detail_view_uri, content=value).render(safe=True)

    def render_group(self, value):
        return Link(url=value.detail_view_uri, content=value).render(safe=True)

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


class PublishesRequestTable(PendingRequestTable):
    class Meta:
        model = PublishRequest
        fields = ('group', 'organization', 'message')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'publishers-for-table'


class GroupInvitationRequestTable(tables.Table):
    class Meta:
        model = PublishRequest
        fields = ('user', 'group', 'message')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'group-invitation-table'


class OrganizationDetailTable(tables.Table):
    class Meta:
        model = Organization
        fields = ('organization_name',
                  'parent',
                  'is_auto_generated',
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


class OrganizationTable(ActionTableMixin, tables.Table):
    class Meta:
        model = Organization
        fields = ('organization_name', 'description', 'is_auto_generated', 'parent')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'organizations-table'

    caption = _("Shows all organizations which are configured in your Mr. Map environment.")

    def before_render(self, request):
        self.render_helper = RenderHelper(user_permissions=list(filter(None, request.user.get_all_permissions())))

    def render_organization_name(self, value, record):
        return Link(url=record.detail_view_uri, content=value).render(safe=True)

    @staticmethod
    def render_is_auto_generated(value):
        """ Preprocessing for rendering of is_auto_generated value.

        Due to semantic reasons, we invert this value.

        Args:
            value: The value
        Returns:

        """
        return get_ok_nok_icon(value)

    def render_actions(self, record):
        self.render_helper.update_attrs = {"class": ["mr-1"]}
        rendered = self.render_helper.render_list_coherent(items=record.get_actions())
        self.render_helper.update_attrs = None
        return format_html(rendered)


class OrganizationMemberTable(ActionTableMixin, tables.Table):
    class Meta:
        model = get_user_model()
        fields = ('username', )
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"

    def __init__(self, organization: Organization, *args, **kwargs):
        self.organization = organization
        super().__init__(*args, **kwargs)

    def before_render(self, request):
        self.render_helper = RenderHelper(user_permissions=list(filter(None, request.user.get_all_permissions())))

    def render_actions(self):
        remove_icon = Tag(tag='i', attrs={"class": [IconEnum.DELETE.value]}).render()
        st_edit_text = Tag(tag='div', attrs={"class": ['d-lg-none']}, content=remove_icon).render()
        gt_edit_text = Tag(tag='div', attrs={"class": ['d-none', 'd-lg-block']},
                           content=remove_icon + _(' Remove').__str__()).render()
        btns = [

        ]
        return format_html(self.render_helper.render_list_coherent(items=btns))


class OrganizationPublishersTable(ActionTableMixin, tables.Table):
    class Meta:
        model = Organization
        fields = ('organization_name', )
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'publishers-table'

    def __init__(self, organization, *args, **kwargs):
        self.organization = organization
        super().__init__(*args, **kwargs)

    def before_render(self, request):
        self.render_helper = RenderHelper(user_permissions=list(filter(None, request.user.get_all_permissions())))

    def render_name(self, record, value):
        return Link(url=record.detail_view_uri, content=value).render(safe=True)

    def render_actions(self, record):
        remove_icon = Tag(tag='i', attrs={"class": [IconEnum.DELETE.value]}).render()
        st_edit_text = Tag(tag='div', attrs={"class": ['d-lg-none']}, content=remove_icon).render()
        gt_edit_text = Tag(tag='div', attrs={"class": ['d-none', 'd-lg-block']},
                           content=remove_icon + _(' Remove').__str__()).render()

        publishers_querystring = "publishers"
        publishers_excluded_record = self.organization.publishers.exclude(pk=record.pk)
        if publishers_excluded_record:
            publishers_querystring = ""
            for is_last_element, publisher in signal_last(publishers_excluded_record):
                if is_last_element:
                    publishers_querystring += f"publishers={publisher.pk}"
                else:
                    publishers_querystring += f"publishers={publisher.pk}&"

        btns = [
            LinkButton(url=f"{self.organization.edit_view_uri}?{publishers_querystring}",
                       content=st_edit_text + gt_edit_text,
                       color=ButtonColorEnum.DANGER,
                       tooltip=_(f"Remove <strong>{record}</strong> from <strong>{self.organization}</strong>"),
                       tooltip_placement=TooltipPlacementEnum.LEFT)
        ]
        return format_html(self.render_helper.render_list_coherent(items=btns))


class MrMapUserTable(ActionTableMixin, tables.Table):
    class Meta:
        model = get_user_model()
        fields = ('username', 'organization', 'groups')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"

    def before_render(self, request):
        self.render_helper = RenderHelper(user_permissions=list(filter(None, request.user.get_all_permissions())))

    def render_organization(self, value):
        return Link(url=value.detail_view_uri, content=value).render(safe=True)

    def render_groups(self, record, value):
        links = []
        for group in value.all():
            link = Link(url=group.mrmapgroup.detail_view_uri, content=group.mrmapgroup)
            link_with_seperator = Tag(tag='span', content=link + ',')
            links.append(link_with_seperator)
        self.render_helper.update_attrs = {"class": ["mr-1"]}
        renderd_actions = self.render_helper.render_list_coherent(items=links)
        self.render_helper.update_attrs = None
        return format_html(renderd_actions)

    def render_actions(self, record):
        remove_icon = Tag(tag='i', attrs={"class": [IconEnum.ADD.value]}).render()
        st_invite_text = Tag(tag='div', attrs={"class": ['d-lg-none']}, content=remove_icon).render()
        gt_invite_text = Tag(tag='div', attrs={"class": ['d-none', 'd-lg-block']},
                             content=remove_icon + _(' Invite').__str__()).render()
        btns = [
            LinkButton(url=f"{record.invite_to_group_url}",
                       content=st_invite_text + gt_invite_text,
                       color=ButtonColorEnum.SUCCESS,
                       tooltip=_(f"Invite <strong>{record}</strong>"),
                       tooltip_placement=TooltipPlacementEnum.LEFT)
        ]
        return format_html(self.render_helper.render_list_coherent(items=btns))
