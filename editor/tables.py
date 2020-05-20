import django_tables2 as tables
from django.utils.html import format_html
from django.urls import reverse

from MrMap.tables import MrMapTable
from service.models import Layer, FeatureType
from MrMap.consts import *
from MrMap.utils import get_theme, get_ok_nok_icon
from django.utils.translation import gettext_lazy as _


def _get_edit_button(url, user):
    return format_html(URL_BTN_PATTERN,
                       BTN_CLASS,
                       BTN_SM_CLASS,
                       get_theme(user)["TABLE"]["BTN_WARNING_COLOR"],
                       url,
                       format_html(get_theme(user)["ICONS"]['EDIT']),)


def _get_undo_button(url, user):
    return format_html(URL_BTN_PATTERN,
                       BTN_CLASS,
                       BTN_SM_CLASS,
                       get_theme(user)["TABLE"]["BTN_DANGER_COLOR"],
                       url,
                       format_html(get_theme(user)["ICONS"]['UNDO']),)


class WmsServiceTable(MrMapTable):
    caption = _("Shows all WMS which are configured in your Mr. Map environment. You can Edit them if you want.")

    wms_title = tables.Column(accessor='title', verbose_name=_('Title'), )
    wms_active = tables.Column(accessor='is_active', verbose_name=_('Active'), )
    wms_data_provider = tables.Column(accessor='contact.organization_name', verbose_name=_('Data provider'), )
    wms_registered_by_group = tables.Column(accessor='service.created_by', verbose_name=_('Registered by group'), )
    wms_original_metadata = tables.Column(verbose_name=_('Original metadata'), empty_values=[])
    wms_secured_access = tables.Column(accessor='is_secured', verbose_name=_('Secured access'), )
    wms_last_modified = tables.Column(accessor='last_modified', verbose_name=_('Last modified'), )
    wms_edit_metadata = tables.Column(verbose_name=_('Edit'), empty_values=[])
    wms_edit_access = tables.Column(verbose_name=_('Access'), empty_values=[])
    wms_reset = tables.Column(verbose_name=_('Reset'), empty_values=[])

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)

    def render_wms_title(self, value, record):
        url = reverse('service:detail', args=(record.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )

    @staticmethod
    def render_wms_active(value):
        return get_ok_nok_icon(value)

    def render_wms_data_provider(self, value, record):
        url = reverse('structure:detail-organization', args=(record.contact.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )

    def render_wms_registered_by_group(self, value, record):
        url = reverse('structure:detail-group', args=(record.service.created_by.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )

    @staticmethod
    def render_wms_original_metadata(record):
        count = Layer.objects.filter(parent_service__metadata=record, metadata__is_custom=True).count()
        if not record.is_custom and count == 0:
            return get_ok_nok_icon(True)
        else:
            return get_ok_nok_icon(False)

    @staticmethod
    def render_wms_secured_access(value):
        return get_ok_nok_icon(value)

    def render_wms_edit_metadata(self, record):
        url = reverse('editor:edit', args=(record.id,))
        return _get_edit_button(url, self.user)

    def render_wms_edit_access(self, record):
        url = reverse('editor:edit_access', args=(record.id,))
        return _get_edit_button(url, self.user)

    def render_wms_reset(self, record):
        url = reverse('editor:restore', args=(record.id,))
        return _get_undo_button(url, self.user)


class WfsServiceTable(MrMapTable):
    caption = _("Shows all WFS which are configured in your Mr. Map environment. You can Edit them if you want.")

    wfs_title = tables.Column(accessor='title', verbose_name=_('Title'), )
    wfs_active = tables.Column(accessor='is_active', verbose_name=_('Active'), )
    wfs_data_provider = tables.Column(accessor='contact.organization_name', verbose_name=_('Data provider'), )
    wfs_registered_by_group = tables.Column(accessor='service.created_by', verbose_name=_('Registered by group'), )
    wfs_original_metadata = tables.Column(verbose_name=_('Original metadata'), empty_values=[])
    wfs_secured_access = tables.Column(accessor='is_secured', verbose_name=_('Secured access'), )
    wfs_last_modified = tables.Column(accessor='last_modified', verbose_name=_('Last modified'), )
    wfs_edit_metadata = tables.Column(verbose_name=_('Edit'), empty_values=[])
    wfs_edit_access = tables.Column(verbose_name=_('Access'), empty_values=[])
    wfs_reset = tables.Column(verbose_name=_('Reset'), empty_values=[])

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)

    def render_wfs_title(self, value, record):
        url = reverse('service:detail', args=(record.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )

    @staticmethod
    def render_wfs_active(value):
        return get_ok_nok_icon(value)

    def render_wfs_data_provider(self, value, record):
        url = reverse('structure:detail-organization', args=(record.contact.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )

    def render_wfs_registered_by_group(self, value, record):
        url = reverse('structure:detail-group', args=(record.service.created_by.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )

    @staticmethod
    def render_wfs_original_metadata(record):
        count = FeatureType.objects.filter(parent_service__metadata=record, metadata__is_custom=True)
        if not record.is_custom and count == 0:
            return get_ok_nok_icon(True)
        else:
            return get_ok_nok_icon(False)

    @staticmethod
    def render_wfs_secured_access(value):
        return get_ok_nok_icon(value)

    def render_wfs_edit_metadata(self, record):
        url = reverse('editor:edit', args=(record.id,))
        return _get_edit_button(url, self.user)

    def render_wfs_edit_access(self, record):
        url = reverse('editor:edit_access', args=(record.id,))
        return _get_edit_button(url, self.user)

    def render_wfs_reset(self, record):
        url = reverse('editor:restore', args=(record.id,))
        return _get_undo_button(url, self.user)


class DatasetTable(MapSkinnerTable):
    caption = _("Shows all datasets which are configured in your Mr. Map environment. You can Edit them if you want.")

    dataset_title = tables.Column(accessor='title', verbose_name=_('Title'), )
    dataset_related_objects = tables.Column(verbose_name=_('Related objects'), empty_values=[])
    dataset_edit_metadata = tables.Column(verbose_name=_('Edit'), empty_values=[])
    dataset_reset = tables.Column(verbose_name=_('Reset'), empty_values=[])

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)

    def render_dataset_title(self, value, record):
        url = reverse('service:get-dataset-metadata', args=(record.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )

    def render_dataset_related_objects(self, record):
        relations = MetadataRelation.objects.filter(metadata_to=record)
        link_list = []
        for relation in relations:
            url = reverse('service:detail', args=(relation.metadata_from.id,))
            link_list.append(format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, relation.metadata_from.title, ))
        return format_html(', '.join(link_list))

    def render_dataset_edit_metadata(self, record):
        url = reverse('editor:edit', args=(record.id,))
        return _get_edit_button(url, self.user)

    def render_dataset_reset(self, record):
        url = reverse('editor:restore', args=(record.id,))
        return _get_undo_button(url, self.user)
