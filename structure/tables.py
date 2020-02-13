import django_tables2 as tables
from django.utils.html import format_html
from django.urls import reverse
from structure.models import Group, Organization
from MapSkinner.settings import THEME, DARK_THEME, LIGHT_THEME

URL_PATTERN = "<a class={} href='{}'>{}</a>"


# TODO: refactor this; this function should be global
def _get_theme():
    if THEME == 'DARK':
        return DARK_THEME
    else:
        return LIGHT_THEME

class GroupTable(tables.Table):
    groups_name = tables.Column(accessor='name', verbose_name='Name', )
    groups_description = tables.Column(accessor='description', verbose_name='Description', )
    groups_organization = tables.Column(accessor='organization', verbose_name='Organization', )

    @staticmethod
    def render_groups_name(value, record):
        url = reverse('structure:detail-group', args=(record.id,))
        return format_html(URL_PATTERN, _get_theme()["TABLE"]["LINK_COLOR"], url, value, )

    @staticmethod
    def render_groups_organization(value, record):
        url = reverse('structure:detail-organization', args=(record.id,))
        return format_html(URL_PATTERN, _get_theme()["TABLE"]["LINK_COLOR"], url, value, )


class OrganizationTable(tables.Table):
    orgs_organization_name = tables.Column(accessor='organization_name', verbose_name='Name', )
    orgs_description = tables.Column(accessor='description', verbose_name='Description', )
    orgs_is_auto_generated = tables.Column(accessor='is_auto_generated', verbose_name='Real organization', )
    orgs_parent = tables.Column(accessor='parent', verbose_name='Parent',)

    @staticmethod
    def render_orgs_organization_name(value, record):
        url = reverse('structure:detail-organization', args=(record.id,))
        return format_html(URL_PATTERN, _get_theme()["TABLE"]["LINK_COLOR"], url, value, )

    @staticmethod
    def render_orgs_is_auto_generated(value):
        if not value:
            return format_html("<i class='fas fa-check text-success'></i>")
        else:
            return format_html("<i class='fas fa-times text-danger'></i>")
