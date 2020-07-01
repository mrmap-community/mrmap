import django_tables2 as tables
from django.template.loader import render_to_string
from django.urls import reverse

from MrMap.forms import MrMapConfirmForm
from MrMap.tables import MrMapTable
from service.models import Layer, FeatureType, MetadataRelation
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


def _get_delete_button(url, user):
    return format_html(URL_BTN_PATTERN,
                       BTN_CLASS,
                       BTN_SM_CLASS,
                       get_theme(user)["TABLE"]["BTN_DANGER_COLOR"],
                       url,
                       format_html(get_theme(user)["ICONS"]["REMOVE"]),)


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
        btns = "{} {}"
        # ToDo: only add buttons if the user has the permission for it
        context_edit_btn = {
            "btn_size": BTN_SM_CLASS,
            "btn_color": get_theme(self.user)["TABLE"]["BTN_WARNING_COLOR"],
            "btn_value": get_theme(self.user)["ICONS"]['EDIT'],
            # ToDo 'editor:index' has to be a dynamic value from the current view where the user comes from
            "btn_url": reverse('editor:dataset-metadata-wizard-instance', args=('editor:index', record.id)),
            "tooltip": format_html(_("Edit {} [{}] dataset"), record.title, record.id),
            "tooltip_placement": "left",
        }
        edit_btn = render_to_string(template_name="sceletons/open-link-button.html",
                                    context=context_edit_btn)

        context_restore_btn = {
            "btn_size": BTN_SM_CLASS,
            "btn_color": get_theme(self.user)["TABLE"]["BTN_DANGER_COLOR"],
            "id_modal": f"restore_dataset_{record.id}",
            "btn_value": get_theme(self.user)["ICONS"]['UNDO'],
            "tooltip": format_html(_("Restore <strong>{} [{}]</strong> dataset"), record.title, record.id),
            "tooltip_placement": "left",
        }
        restore_btn = render_to_string(template_name="sceletons/open-modal-button.html",
                                       context=context_restore_btn)
        context_restore_modal = {
            "metadata": record,
            "form": MrMapConfirmForm(request=self.request,
                                     action_url=reverse('editor:restore-dataset-metadata', args=(record.id,)),
                                     is_confirmed_label=_("Do you really want to restore this dataset?"),),
            "id_modal": f"restore_dataset_{record.id}",
            "THEME": get_theme(self.user),
            "modal_title": format_html("Restore dataset <strong>{} [{}]</strong>", record.title, record.id),
            "modal_submit_btn_content": format_html("{} {}", get_theme(self.user)["ICONS"]['UNDO'], _('Restore'))
        }
        restore_modal = render_to_string(request=self.request,
                                         template_name="modals/confirm_modal.html",
                                         context=context_restore_modal)
        restore_trailer = format_html("{}{}", restore_btn, restore_modal)

        context_remove_btn = {
            "btn_size": BTN_SM_CLASS,
            "btn_color": get_theme(self.user)["TABLE"]["BTN_DANGER_COLOR"],
            "id_modal": f"remove_dataset_{record.id}",
            "btn_value": get_theme(self.user)["ICONS"]['REMOVE'],
            "tooltip": format_html(_("Remove <strong>{} [{}]</strong> dataset"), record.title, record.id),
            "tooltip_placement": "left",
            }
        remove_btn = render_to_string(template_name="sceletons/open-modal-button.html",
                                      context=context_remove_btn)
        context_remove_modal = {
            "metadata": record,
            "form": MrMapConfirmForm(request=self.request,
                                     action_url=reverse("editor:remove-dataset-metadata", args=(record.id, )),
                                     is_confirmed_label=_("Do you really want to delete this dataset?")),
            "id_modal": f"remove_dataset_{record.id}",
            "THEME": get_theme(self.user),
            "modal_title": format_html("Remove dataset <strong>{} [{}]</strong>", record.title, record.id),
            "modal_submit_btn_content": format_html("{} {}", get_theme(self.user)["ICONS"]['REMOVE'], _('Remove'))
        }
        remove_modal = render_to_string(request=self.request,
                                        template_name="modals/confirm_modal.html",
                                        context=context_remove_modal)
        remove_trailer = format_html("{}{}", remove_btn, remove_modal)

        relations = MetadataRelation.objects.filter(metadata_to=record)
        is_mr_map_origin = True
        for relation in relations:
            if relation.origin.name != "MrMap":
                is_mr_map_origin = False
                break

        if is_mr_map_origin:
            btns = format_html(btns, edit_btn, remove_trailer)
        else:
            btns = format_html(btns, edit_btn, restore_trailer)

        return btns
