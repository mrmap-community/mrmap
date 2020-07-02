import django_tables2 as tables
from django.urls import reverse
from MrMap.tables import MrMapTable
from service.filters import MetadataDatasetFilter, MetadataWfsFilter
from service.models import Layer, FeatureType, MetadataRelation
from MrMap.consts import *
from MrMap.utils import get_theme, get_ok_nok_icon
from django.utils.translation import gettext_lazy as _
from structure.models import Permission


def _get_action_btns_for_service_table(self, record):
    btns = ''
    btns += self.get_btn(
        href=reverse('editor:edit', args=(record.id, self.current_view)),
        btn_color=get_theme(self.user)["TABLE"]["BTN_WARNING_COLOR"],
        btn_value=get_theme(self.user)["ICONS"]['EDIT'],
        permission=Permission(can_edit_metadata_service=True),
        tooltip=format_html(_(f"Edit metadata of <strong>{record.title} [{record.id}]</strong>"), ),
        tooltip_placement='left', )

    btns += self.get_btn(
        href=reverse('editor:edit_access', args=(record.id,)),
        btn_color=get_theme(self.user)["TABLE"]["BTN_WARNING_COLOR"],
        btn_value=get_theme(self.user)["ICONS"]['EDIT'],
        permission=Permission(can_edit_metadata_service=True),
        tooltip=format_html(_(f"Edit access of <strong>{record.title} [{record.id}]</strong> service"), ),
        tooltip_placement='left', )

    btns += self.get_btn(
        href=reverse('editor:restore', args=(record.id, self.current_view)),
        btn_color=get_theme(self.user)["TABLE"]["BTN_DANGER_COLOR"],
        btn_value=get_theme(self.user)["ICONS"]['UNDO'],
        permission=Permission(can_edit_metadata_service=True),
        tooltip=format_html(_(f"Restore <strong>{record.title} [{record.id}]</strong> metadata"), ),
        tooltip_placement='left',
    )
    return format_html(btns)


class WmsServiceTable(MrMapTable):
    caption = _("Shows all WMS which are configured in your Mr. Map environment. You can Edit them if you want.")

    wms_title = tables.Column(accessor='title', verbose_name=_('Title'), )
    wms_active = tables.Column(accessor='is_active', verbose_name=_('Active'), )
    wms_data_provider = tables.Column(accessor='contact.organization_name', verbose_name=_('Data provider'), )
    wms_registered_by_group = tables.Column(accessor='service.created_by', verbose_name=_('Registered by group'), )
    wms_original_metadata = tables.Column(verbose_name=_('Original metadata'), empty_values=[])
    wms_secured_access = tables.Column(accessor='is_secured', verbose_name=_('Secured access'), )
    wms_last_modified = tables.Column(accessor='last_modified', verbose_name=_('Last modified'), )
    wms_actions = tables.Column(verbose_name=_('Actions'), orderable=False, empty_values=[])

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

    def render_wms_actions(self, record):
        return _get_action_btns_for_service_table(self, record)


class WfsServiceTable(MrMapTable):
    caption = _("Shows all WFS which are configured in your Mr. Map environment. You can Edit them if you want.")

    wfs_title = tables.Column(accessor='title', verbose_name=_('Title'), )
    wfs_active = tables.Column(accessor='is_active', verbose_name=_('Active'), )
    wfs_data_provider = tables.Column(accessor='contact.organization_name', verbose_name=_('Data provider'), )
    wfs_registered_by_group = tables.Column(accessor='service.created_by', verbose_name=_('Registered by group'), )
    wfs_original_metadata = tables.Column(verbose_name=_('Original metadata'), empty_values=[])
    wfs_secured_access = tables.Column(accessor='is_secured', verbose_name=_('Secured access'), )
    wfs_last_modified = tables.Column(accessor='last_modified', verbose_name=_('Last modified'), )
    wfs_actions = tables.Column(verbose_name=_('Actions'), orderable=False, empty_values=[])

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

    def render_wfs_actions(self, record):
        return _get_action_btns_for_service_table(self, record)


class DatasetTable(MrMapTable):
    caption = _("Shows all datasets which are configured in your Mr. Map environment. You can Edit them if you want.")

    dataset_title = tables.Column(accessor='title', verbose_name=_('Title'), )
    dataset_related_objects = tables.Column(verbose_name=_('Related objects'), empty_values=[])
    dataset_origins = tables.Column(verbose_name=_('Origins'), empty_values=[])
    dataset_actions = tables.Column(verbose_name=_('Actions'), empty_values=[], orderable=False)

    def render_dataset_title(self, value, record):
        url = reverse('service:get-metadata-html', args=(record.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )

    def render_dataset_related_objects(self, record):
        relations = MetadataRelation.objects.filter(metadata_to=record)
        link_list = []
        for relation in relations:
            url = reverse('service:detail', args=(relation.metadata_from.id,))
            link_list.append(format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, relation.metadata_from.title+' [{}]'.format(relation.metadata_from.id), ))
        return format_html(', '.join(link_list))

    def render_dataset_origins(self, record):
        relations = MetadataRelation.objects.filter(metadata_to=record)
        origin_list = []
        for relation in relations:
            origin_list.append(relation.origin.name+' [{}]'.format(relation.metadata_from.id))
        return format_html(', '.join(origin_list))

    def render_dataset_actions(self, record):
        relations = MetadataRelation.objects.filter(metadata_to=record)
        is_mr_map_origin = True
        for relation in relations:
            if relation.origin.name != "MrMap":
                is_mr_map_origin = False
                break

        btns = ''
        btns += self.get_btn(href=reverse('editor:dataset-metadata-wizard-instance', args=(self.current_view, record.id)),
                             permission=Permission(can_edit_dataset_metadata=True),
                             tooltip=format_html(_(f"Edit <strong>{record.title} [{record.id}]</strong> dataset")),
                             tooltip_placement='left',
                             btn_color=get_theme(self.user)["TABLE"]["BTN_WARNING_COLOR"],
                             btn_value=get_theme(self.user)["ICONS"]['EDIT'],)

        btns += self.get_btn(href=reverse('editor:restore-dataset-metadata', args=(record.id, self.current_view)),
                             permission=Permission(can_restore_dataset_metadata=True),
                             tooltip=format_html(_(f"Restore <strong>{record.title} [{record.id}]</strong> dataset")),
                             tooltip_placement='left',
                             btn_color=get_theme(self.user)["TABLE"]["BTN_DANGER_COLOR"],
                             btn_value=get_theme(self.user)["ICONS"]['UNDO'],
                             ) if not is_mr_map_origin else ''

        btns += self.get_btn(href=reverse('editor:remove-dataset-metadata', args=(record.id, self.current_view)),
                             permission=Permission(can_remove_dataset_metadata=True),
                             tooltip=format_html(_(f"Remove <strong>{record.title} [{record.id}]</strong> dataset"), ),
                             tooltip_placement='left',
                             btn_color=get_theme(self.user)["TABLE"]["BTN_DANGER_COLOR"],
                             btn_value=get_theme(self.user)["ICONS"]['REMOVE'],
                             ) if is_mr_map_origin else ''

        return format_html(btns)
