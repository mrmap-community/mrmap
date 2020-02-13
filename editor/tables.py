import django_tables2 as tables
from django.utils.html import format_html
from django.urls import reverse
from MapSkinner.settings import THEME, DARK_THEME, LIGHT_THEME
from service.models import Layer, FeatureType
from MapSkinner.consts import *


# TODO: refactor this; this function should be global
def _get_theme():
    if THEME == 'DARK':
        return DARK_THEME
    else:
        return LIGHT_THEME


# TODO: refactor this; this function should be global
def _get_icon(self):
    if self:
        return format_html("<i class='fas fa-check text-success'></i>")
    else:
        return format_html("<i class='fas fa-times text-danger'></i>")


class WmsServiceTable(tables.Table):
    wms_title = tables.Column(accessor='title', verbose_name='Title', )
    wms_active = tables.Column(accessor='is_active', verbose_name='Active', )
    wms_data_provider = tables.Column(accessor='contact.organization_name', verbose_name='Data provider', )
    wms_registered_by_group = tables.Column(accessor='service.created_by', verbose_name='Registered by group', )
    wms_original_metadata = tables.Column(verbose_name='Original metadata', empty_values=[])
    wms_secured_access = tables.Column(accessor='is_secured', verbose_name='Secured access', )
    wms_last_modified = tables.Column(accessor='last_modified', verbose_name='Last modified', )
    wms_edit_metadata = tables.Column(verbose_name='Edit', empty_values=[])
    wms_edit_access = tables.Column(verbose_name='Access', empty_values=[])
    wms_reset = tables.Column(verbose_name='Reset', empty_values=[])

    @staticmethod
    def render_wms_title(value, record):
        url = reverse('service:detail', args=(record.id,))
        return format_html(URL_PATTERN, _get_theme()["TABLE"]["LINK_COLOR"], url, value, )

    @staticmethod
    def render_wms_active(value):
        return _get_icon(value)

    @staticmethod
    def render_wms_data_provider(value, record):
        url = reverse('structure:detail-organization', args=(record.contact.id,))
        return format_html(URL_PATTERN, _get_theme()["TABLE"]["LINK_COLOR"], url, value, )

    @staticmethod
    def render_wms_registered_by_group(value, record):
        url = reverse('structure:detail-group', args=(record.service.created_by.id,))
        return format_html(URL_PATTERN, _get_theme()["TABLE"]["LINK_COLOR"], url, value, )

    @staticmethod
    def render_wms_original_metadata(record):
        count = Layer.objects.filter(parent_service__metadata=record, metadata__is_custom=True).count()
        if not record.is_custom and count == 0:
            return _get_icon(True)
        else:
            return _get_icon(False)

    @staticmethod
    def render_wms_secured_access(value):
        return _get_icon(value)

    @staticmethod
    def render_wms_edit_metadata(record):
        url = reverse('editor:edit', args=(record.id,))
        return format_html(URL_PATTERN_BTN_WARNING, url, format_html(_get_theme()["ICONS"]['EDIT']), )

    @staticmethod
    def render_wms_edit_access(record):
        url = reverse('editor:edit_access', args=(record.id,))
        return format_html(URL_PATTERN_BTN_WARNING, url, format_html(_get_theme()["ICONS"]['EDIT']), )

    @staticmethod
    def render_wms_reset(record):
        url = reverse('editor:restore', args=(record.id,))
        return format_html(URL_PATTERN_BTN_DANGER, url, format_html(_get_theme()["ICONS"]['UNDO']), )


class WfsServiceTable(tables.Table):
    wfs_title = tables.Column(accessor='title', verbose_name='Title', )
    wfs_active = tables.Column(accessor='is_active', verbose_name='Active', )
    wfs_data_provider = tables.Column(accessor='contact.organization_name', verbose_name='Data provider', )
    wfs_registered_by_group = tables.Column(accessor='service.created_by', verbose_name='Registered by group', )
    wfs_original_metadata = tables.Column(verbose_name='Original metadata', empty_values=[])
    wfs_secured_access = tables.Column(accessor='is_secured', verbose_name='Secured access', )
    wfs_last_modified = tables.Column(accessor='last_modified', verbose_name='Last modified', )
    wfs_edit_metadata = tables.Column(verbose_name='Edit', empty_values=[])
    wfs_edit_access = tables.Column(verbose_name='Access', empty_values=[])
    wfs_reset = tables.Column(verbose_name='Reset', empty_values=[])

    @staticmethod
    def render_wfs_title(value, record):
        url = reverse('service:detail', args=(record.id,))
        return format_html(URL_PATTERN, _get_theme()["TABLE"]["LINK_COLOR"], url, value, )

    @staticmethod
    def render_wfs_active(value):
        return _get_icon(value)

    @staticmethod
    def render_wfs_data_provider(value, record):
        url = reverse('structure:detail-organization', args=(record.contact.id,))
        return format_html(URL_PATTERN, _get_theme()["TABLE"]["LINK_COLOR"], url, value, )

    @staticmethod
    def render_wfs_registered_by_group(value, record):
        url = reverse('structure:detail-group', args=(record.service.created_by.id,))
        return format_html(URL_PATTERN, _get_theme()["TABLE"]["LINK_COLOR"], url, value, )

    @staticmethod
    def render_wfs_original_metadata(record):
        count = FeatureType.objects.filter(parent_service__metadata=record, metadata__is_custom=True)
        if not record.is_custom and count == 0:
            return _get_icon(True)
        else:
            return _get_icon(False)

    @staticmethod
    def render_wfs_secured_access(value):
        return _get_icon(value)

    @staticmethod
    def render_wfs_edit_metadata(record):
        url = reverse('editor:edit', args=(record.id,))
        return format_html(URL_PATTERN_BTN_WARNING, url, format_html(_get_theme()["ICONS"]['EDIT']), )

    @staticmethod
    def render_wfs_edit_access(record):
        url = reverse('editor:edit_access', args=(record.id,))
        return format_html(URL_PATTERN_BTN_WARNING, url, format_html(_get_theme()["ICONS"]['EDIT']), )

    @staticmethod
    def render_wfs_reset(record):
        url = reverse('editor:restore', args=(record.id,))
        return format_html(URL_PATTERN_BTN_DANGER, url, format_html(_get_theme()["ICONS"]['UNDO']), )
