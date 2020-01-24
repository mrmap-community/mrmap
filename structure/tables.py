import django_tables2 as tables
from django.utils.html import format_html
from django.urls import reverse
from structure.models import Group, Organization


class GroupTable(tables.Table):
    model = Group

    groups_name = tables.Column(accessor='name', verbose_name='Name', )
    groups_description = tables.Column(accessor='description', verbose_name='Description', )
    groups_organization = tables.Column(accessor='organization', verbose_name='Organization', )

    @staticmethod
    def render_groups_name(value, record):
        url = reverse('structure:detail-group', args=(record.id,))
        return format_html("<a href='{}'>{}</a>", url, value,)

    @staticmethod
    def render_groups_organization(value, record):
        url = reverse('structure:detail-organization', args=(record.id,))
        return format_html("<a href='{}'>{}</a>", url, value, )


class OrganizationTable(tables.Table):
    model = Organization

    orgs_organization_name = tables.Column(accessor='organization_name', verbose_name='Name', )
    orgs_description = tables.Column(accessor='description', verbose_name='Description', )
    orgs_is_auto_generated = tables.Column(accessor='is_auto_generated', verbose_name='Real organization', )
    orgs_parent = tables.Column(accessor='parent', verbose_name='Parent',)

    @staticmethod
    def render_orgs_organization_name(value, record):
        url = reverse('structure:detail-organization', args=(record.id,))
        return format_html("<a href='{}'>{}</a>", url, value,)

    @staticmethod
    def render_orgs_is_auto_generated(value):
        if not value:
            return format_html("<i class='fas fa-check text-success'></i>")
        else:
            return format_html("<i class='fas fa-times text-danger'></i>")
