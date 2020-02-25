import django_tables2 as tables
from django.utils.html import format_html
from django.urls import reverse
from MapSkinner.utils import get_theme, get_ok_nok_icon
from MapSkinner.consts import URL_PATTERN


class GroupTable(tables.Table):
    groups_name = tables.Column(accessor='name', verbose_name='Name', )
    groups_description = tables.Column(accessor='description', verbose_name='Description', )
    groups_organization = tables.Column(accessor='organization', verbose_name='Organization', )

    @staticmethod
    def render_groups_name(value, record):
        url = reverse('structure:detail-group', args=(record.id,))
        return format_html(URL_PATTERN, get_theme()["TABLE"]["LINK_COLOR"], url, value, )

    @staticmethod
    def render_groups_organization(value, record):
        url = reverse('structure:detail-organization', args=(record.id,))
        return format_html(URL_PATTERN, get_theme()["TABLE"]["LINK_COLOR"], url, value, )


class OrganizationTable(tables.Table):
    orgs_organization_name = tables.Column(accessor='organization_name', verbose_name='Name', )
    orgs_description = tables.Column(accessor='description', verbose_name='Description', )
    orgs_is_auto_generated = tables.Column(accessor='is_auto_generated', verbose_name='Real organization', )
    orgs_parent = tables.Column(accessor='parent', verbose_name='Parent',)

    @staticmethod
    def render_orgs_organization_name(value, record):
        url = reverse('structure:detail-organization', args=(record.id,))
        return format_html(URL_PATTERN, get_theme()["TABLE"]["LINK_COLOR"], url, value, )

    @staticmethod
    def render_orgs_is_auto_generated(value):
        return get_ok_nok_icon(value)
