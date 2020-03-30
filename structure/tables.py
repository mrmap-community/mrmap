import django_tables2 as tables
from django.template.loader import render_to_string
from django.utils.html import format_html
from django.urls import reverse

from MapSkinner.tables import MapSkinnerTable
from MapSkinner.utils import get_theme, get_ok_nok_icon
from MapSkinner.consts import URL_PATTERN
from django.utils.translation import gettext_lazy as _


class PublisherTable(MapSkinnerTable):
    class Meta:
        row_attrs = {
            "class": "text-center"
        }
    publisher_group = tables.Column(accessor='name', verbose_name='Group')
    publisher_org = tables.Column(accessor='organization', verbose_name='Group organization')
    publisher_action = tables.TemplateColumn(
        template_name="includes/detail/publisher_requests_accept_reject.html",
        verbose_name='Action',
        orderable=False,
        extra_context={
            "remove_publisher": True,
        }
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)

    def render_publisher_group(self, value, record):
        """ Renders publisher_group as link to detail view of group

        Args:
            value:
            record:
        Returns:

        """
        url = reverse('structure:detail-group', args=(record.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )

    def render_publisher_org(self, value, record):
        """ Renders publisher_org as link to detail view of organization

        Args:
            value:
            record:
        Returns:

        """
        url = reverse('structure:detail-organization', args=(record.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )


class PublishesForTable(MapSkinnerTable):
    class Meta:
        row_attrs = {
            "class": "text-center"
        }
    publisher_org = tables.Column(accessor='organization_name', verbose_name='Organization')
    publisher_action = tables.TemplateColumn(
        template_name="includes/detail/publisher_requests_accept_reject.html",
        verbose_name='Action',
        orderable=False,
        extra_context={
            "remove_publisher": True,
            "publishes_for": True,
        }
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)

    def render_publisher_org(self, value, record):
        """ Renders publisher_org as link to detail view of organization

        Args:
            value:
            record:
        Returns:

        """
        url = reverse('structure:detail-organization', args=(record.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )


class PublisherRequestTable(MapSkinnerTable):
    class Meta:
        row_attrs = {
            "class": "text-center"
        }
    publisher_group = tables.Column(accessor='group', verbose_name='Group')
    publisher_org = tables.Column(accessor='group.organization', verbose_name='Group organization')
    message = tables.Column(accessor='message', verbose_name='Message')
    activation_until = tables.Column(accessor='activation_until', verbose_name='Activation until')
    publisher_action = tables.TemplateColumn(
        template_name="includes/detail/publisher_requests_accept_reject.html",
        verbose_name='Action',
        orderable=False,
        extra_context={
        }
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)

    def render_publisher_group(self, value, record):
        """ Renders publisher_group as link to detail view of group

        Args:
            value:
            record:
        Returns:

        """
        url = reverse('structure:detail-group', args=(record.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )

    def render_publisher_org(self, value, record):
        """ Renders publisher_org as link to detail view of organization

        Args:
            value:
            record:
        Returns:

        """
        url = reverse('structure:detail-organization', args=(record.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )


class GroupTable(MapSkinnerTable):
    groups_name = tables.Column(accessor='name', verbose_name='Name', )
    groups_description = tables.Column(accessor='description', verbose_name='Description', )
    groups_organization = tables.Column(accessor='organization', verbose_name='Organization', )

    caption = _("Shows all groups which are configured in your Mr. Map environment.")

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)

    def render_groups_name(self, value, record):
        url = reverse('structure:detail-group', args=(record.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )

    def render_groups_organization(self, value, record):
        url = reverse('structure:detail-organization', args=(record.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )


class OrganizationTable(MapSkinnerTable):
    orgs_organization_name = tables.Column(accessor='organization_name', verbose_name='Name', )
    orgs_description = tables.Column(accessor='description', verbose_name='Description', )
    orgs_is_auto_generated = tables.Column(accessor='is_auto_generated', verbose_name='Real organization', )
    orgs_parent = tables.Column(accessor='parent', verbose_name='Parent',)

    caption = _("Shows all organizations which are configured in your Mr. Map environment.")

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)

    def render_orgs_organization_name(self, value, record):
        url = reverse('structure:detail-organization', args=(record.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )

    @staticmethod
    def render_orgs_is_auto_generated(value):
        """ Preprocessing for rendering of is_auto_generated value.

        Due to semantic reasons, we invert this value.

        Args:
            value: The value
        Returns:

        """
        val = not value
        return get_ok_nok_icon(val)
