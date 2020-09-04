import csv

import django_tables2 as tables
from django.db.models.functions import Length
from django.utils.html import format_html
from django.urls import reverse
import json

from MrMap.columns import MrMapColumn
from MrMap.tables import MrMapTable
from MrMap.utils import get_theme
from django.db.models import Count
from django.utils.translation import gettext_lazy as _

from csw.models import HarvestResult
from monitoring.enums import HealthStateEnum
from monitoring.settings import DEFAULT_UNKNOWN_MESSAGE, WARNING_RELIABILITY, CRITICAL_RELIABILITY
from service.helper.enums import ResourceOriginEnum, PendingTaskEnum
from service.models import MetadataRelation, Metadata
from structure.permissionEnums import PermissionEnum


def _get_action_btns_for_service_table(table, record):
    btns = ''
    btns += table.get_btn(
        href=reverse('resource:activate', args=(record.id, ))+f"?current-view={table.current_view}",
        btn_color=get_theme(table.user)["TABLE"]["BTN_WARNING_COLOR" if record.is_active else "BTN_SUCCESS_COLOR"],
        btn_value=get_theme(table.user)["ICONS"]["POWER_OFF"],
        permission=PermissionEnum.CAN_EDIT_METADATA,
        tooltip=format_html(_("Deactivate") if record.is_active else _("Activate")),
        tooltip_placement='left', )

    btns += table.get_btn(
        href=reverse('resource:new-pending-update', args=(record.id, ))+f"?current-view={table.current_view}",
        btn_color=get_theme(table.user)["TABLE"]["BTN_INFO_COLOR"],
        btn_value=get_theme(table.user)["ICONS"]['UPDATE'],
        permission=PermissionEnum.CAN_UPDATE_RESOURCE,
        tooltip=format_html(_("Update"), ),
        tooltip_placement='left', )

    btns += table.get_btn(
        href=reverse('monitoring:run-monitoring', args=(record.id, ))+f"?current-view={table.current_view}",
        btn_color=get_theme(table.user)["TABLE"]["BTN_INFO_COLOR"],
        btn_value=get_theme(table.user)["ICONS"]['HEARTBEAT'],
        permission=PermissionEnum.CAN_RUN_MONITORING,
        tooltip=format_html(_("Run health check"), ),
        tooltip_placement='left', )

    btns += table.get_btn(
        href=reverse('editor:edit', args=(record.id,)) + f"?current-view={table.current_view}",
        btn_color=get_theme(table.user)["TABLE"]["BTN_WARNING_COLOR"],
        btn_value=get_theme(table.user)["ICONS"]['EDIT'],
        permission=PermissionEnum.CAN_EDIT_METADATA,
        tooltip=format_html(_("Edit metadata"), ),
        tooltip_placement='left', )

    btns += table.get_btn(
        href=reverse('editor:edit_access', args=(record.id,)),
        btn_color=get_theme(table.user)["TABLE"]["BTN_WARNING_COLOR"],
        btn_value=get_theme(table.user)["ICONS"]['ACCESS'],
        permission=PermissionEnum.CAN_EDIT_METADATA,
        tooltip=format_html(_("Edit access"), ),
        tooltip_placement='left', )

    btns += table.get_btn(
        href=reverse('editor:restore', args=(record.id, ))+f"?current-view={table.current_view}",
        btn_color=get_theme(table.user)["TABLE"]["BTN_DANGER_COLOR"],
        btn_value=get_theme(table.user)["ICONS"]['UNDO'],
        permission=PermissionEnum.CAN_EDIT_METADATA,
        tooltip=format_html(_("Restore metadata"), ),
        tooltip_placement='left',
    )

    btns += table.get_btn(
        href=reverse('resource:remove', args=(record.id,)) + f"?current-view={table.current_view}",
        btn_color=get_theme(table.user)["TABLE"]["BTN_DANGER_COLOR"],
        btn_value=get_theme(table.user)["ICONS"]['REMOVE'],
        permission=PermissionEnum.CAN_REMOVE_RESOURCE,
        tooltip=format_html(_("Remove"), ),
        tooltip_placement='left',
    )

    if len(btns) == 0:
        # User has no permission for anything!
        btns = _("No permissions!")
    return format_html(btns)


TOOLTIP_TITLE = _('The resource title')
TOOLTIP_ACTIVE = _('Shows whether the resource is active or not.')
TOOLTIP_SECURED_ACCESS = _('Shows whether the resource is only accessible for certain groups and/or in certain areas.')
TOOLTIP_SECURED_EXTERNALLY = _('Shows whether the resource needs authentication to its origin server.')
TOOLTIP_VERSION = _('The resource version')
TOOLTIP_DATA_PROVIDER = _('The organization which provides the resource.')
TOOLTIP_REGISTERED_BY_GROUP = _('The group which registered the resource.')
TOOLTIP_REGISTERED_FOR = _('The organization for which the resource is registered.')
TOOLTIP_CREATED_ON = _('The registration date.')
TOOLTIP_ACTIONS = _('Performable Actions')
TOOLTIP_STATUS = _('Shows the status of the resource. You can see active state, secured access state and secured externally state.')
TOOLTIP_HEALTH = _('Shows the health status of the resource.')


class ResourceTable(MrMapTable):
    def get_status_icons(self, record):
        icons = ''
        if record.is_active:
            icons += self.get_icon(icon_color='text-success',
                                   icon=get_theme(self.user)["ICONS"]["POWER_OFF"],
                                   tooltip=_('This resource is active.'))
        else:
            icons += self.get_icon(icon_color='text-danger',
                                   icon=get_theme(self.user)["ICONS"]["POWER_OFF"],
                                   tooltip=_('This resource is deactivated.'))
        if record.is_secured:
            icons += self.get_icon(icon=get_theme(self.user)["ICONS"]["WFS"],
                                   tooltip=_('This resource is secured.'))
        if hasattr(record, 'external_authentication'):
            icons += self.get_icon(icon=get_theme(self.user)["ICONS"]["PASSWORD"],
                                   tooltip=_('This resource has external authentication.'))

        return format_html(icons)

    def get_health_icons(self, record):
        icons = ''
        health_state = record.get_health_state()
        if health_state:
            if health_state.health_state_code == HealthStateEnum.OK.value:
                # state is OK
                icon_color = 'text-success'
            elif health_state.health_state_code == HealthStateEnum.WARNING.value:
                # state is WARNING
                icon_color = 'text-warning'
            elif health_state.health_state_code == HealthStateEnum.CRITICAL.value:
                # state is CRITICAL
                icon_color = 'text-danger'
            elif health_state.health_state_code == HealthStateEnum.UNKNOWN.value:
                # state is unknown
                icon_color = 'text-secondary'
            tooltip = health_state.health_message
        else:
            # state is unknown
            icon_color = 'text-secondary'
            tooltip = DEFAULT_UNKNOWN_MESSAGE

        icon = self.get_icon(icon_color=icon_color,
                             icon=get_theme(self.user)["ICONS"]["HEARTBEAT"],)

        if health_state and not health_state.health_state_code == HealthStateEnum.UNKNOWN.value:
            icon = self.get_btn(href=reverse('monitoring:health-state', args=(record.id, )),
                                btn_value=icon,
                                btn_color='btn-light',
                                permission=None,
                                tooltip=tooltip,)

        icons += icon

        if health_state:
            for reason in health_state.reasons.all():
                if reason.health_state_code == HealthStateEnum.UNAUTHORIZED.value:
                    icons += self.get_icon(icon_color='text-info',
                                           icon=get_theme(self.user)["ICONS"]["PASSWORD"],
                                           tooltip=_(
                                               'Some checks can\'t get a result, cause the service needs an authentication for this request.'))
                    break

            badge_color = 'badge-success'
            if health_state.reliability_1w < CRITICAL_RELIABILITY:
                badge_color = 'badge-danger'
            elif health_state.reliability_1w < WARNING_RELIABILITY:
                badge_color = 'badge-warning'
            icons += '<br>' + self.get_badge(badge_color=badge_color,
                                             badge_pill=True,
                                             value=f'{round(health_state.reliability_1w, 2)} %',
                                             tooltip=_('Reliability statistic for one week.'))

        return format_html(icons)

    def order_status(self, queryset, is_descending):
        is_descending_str = "-" if is_descending else ""
        queryset = queryset.order_by(is_descending_str + "is_active",
                                     is_descending_str + "is_secured",
                                     is_descending_str + "external_authentication", )
        return queryset, True

    def order_health(self, queryset, is_descending):
        # TODO:
        return queryset, True


class WmsServiceTable(ResourceTable):

    attrs = {
        "th": {
            "class": "align-middle",
        }
    }
    wms_title = MrMapColumn(
        accessor='title',
        verbose_name=_('Title'),
        empty_values=[],
        attrs=attrs,
        tooltip=TOOLTIP_TITLE,
    )
    wms_status = MrMapColumn(
        verbose_name=_('Status'),
        empty_values=[False, ],
        attrs=attrs,
        tooltip=TOOLTIP_STATUS,
    )
    wms_health = MrMapColumn(
        verbose_name=_('Health'),
        empty_values=[False, ],
        attrs=attrs,
        tooltip=TOOLTIP_HEALTH,
    )
    wms_version = MrMapColumn(
        accessor='service.service_type.version',
        verbose_name=_('Version'),
        attrs=attrs,
        tooltip=TOOLTIP_VERSION,
    )
    wms_data_provider = MrMapColumn(
        accessor='contact.organization_name',
        verbose_name=_('Data provider'),
        attrs=attrs,
        tooltip=TOOLTIP_DATA_PROVIDER,
    )
    wms_registered_by_group = MrMapColumn(
        accessor='service.created_by',
        verbose_name=_('Registered by group'),
        attrs=attrs,
        tooltip=TOOLTIP_REGISTERED_BY_GROUP,
    )
    wms_registered_for = MrMapColumn(
        accessor='service.published_for',
        verbose_name=_('Registered for'),
        attrs=attrs,
        tooltip=TOOLTIP_REGISTERED_FOR,
    )
    wms_created_on = MrMapColumn(
        accessor='created',
        verbose_name=_('Created on'),
        attrs=attrs,
        tooltip=TOOLTIP_CREATED_ON,
    )
    wms_actions = MrMapColumn(
        verbose_name=_('Actions'),
        empty_values=[],
        orderable=False,
        tooltip=TOOLTIP_ACTIONS,
        attrs={"td": {"style": "white-space:nowrap;"}}
    )

    def render_wms_title(self, value, record):
        return self.get_link(tooltip=_(f'Click to open the detail view of <strong>{value}</strong>.'),
                             href=reverse('resource:detail', args=(record.id,)),
                             value=value,
                             permission=None)

    def render_wms_status(self, record):
        return self.get_status_icons(record=record)

    def render_wms_health(self, record):
        return self.get_health_icons(record=record)

    def render_wms_data_provider(self, value, record):
        return self.get_link(tooltip=_(f'Click to open the detail view of <strong>{value}</strong>.'),
                             href=reverse('structure:detail-organization', args=(record.contact.id,)),
                             value=value,
                             permission=None)

    def render_wms_registered_by_group(self, value, record):
        return self.get_link(tooltip=_(f'Click to open the detail view of <strong>{value}</strong>.'),
                             href=reverse('structure:detail-group', args=(record.service.created_by.id,)),
                             value=value,
                             permission=None)

    def render_wms_registered_for(self, value, record):
        if record.service.published_for is not None:
            return self.get_link(tooltip=_(f'Click to open the detail view of <strong>{value}</strong>.'),
                                 href=reverse('structure:detail-organization', args=(record.service.published_for.id,)),
                                 value=value,
                                 permission=None)
        else:
            return value

    def render_wms_actions(self, record):
        return _get_action_btns_for_service_table(self, record)

    def order_wms_status(self, queryset, is_descending):
        return self.order_status(queryset=queryset, is_descending=is_descending)

    def order_wms_health(self, queryset, is_descending):
        return self.order_health(queryset=queryset, is_descending=is_descending)


class WmsTableWms(WmsServiceTable):
    caption = _("Shows all registered WMS.")

    attrs = {
        "th": {
            "class": "align-middle",
        }
    }
    wms_layers = tables.Column(verbose_name=_('Layers'), empty_values=[], attrs=attrs)

    class Meta:
        sequence = ("wms_title", "wms_layers", "...")
        row_attrs = {
            "class": "text-center"
        }

    @staticmethod
    def render_wms_layers(record):
        count = record.service.child_service.count()
        return str(count)

    @staticmethod
    def order_wms_layers(queryset, is_descending):
        queryset = queryset.annotate(
            count=Count("service__child_service")
        ).order_by(("-" if is_descending else "") + "count")
        return queryset, True


class WmsLayerTableWms(WmsServiceTable):
    wms_parent_service = MrMapColumn(
        verbose_name=_('Parent service'),
        empty_values=[],
        tooltip=_('The root service of this layer'), )

    caption = _("Shows all registered WMS sublayers.")

    class Meta:
        sequence = ("wms_title", "wms_parent_service", "...")
        row_attrs = {
            "class": "text-center"
        }

    def render_wms_parent_service(self, record):
        return self.get_link(
            tooltip=_('Click to open the detail view of <strong>{}</strong>.'.format(record.service.parent_service.metadata.title)),
            href=reverse('resource:detail', args=(record.service.parent_service.metadata.id,)),
            value=record.service.parent_service.metadata.title,
            permission=None
        )

    @staticmethod
    def order_wms_parent_service(queryset, is_descending):
        queryset = queryset.annotate(
            title_length=Length("service__parent_service__metadata__title")
        ).order_by(("-" if is_descending else "") + "title_length")
        return queryset, True


class WfsServiceTable(ResourceTable):
    caption = _("Shows all registered WFS.")

    class Meta:
        row_attrs = {
            "class": "text-center"
        }

    wfs_title = MrMapColumn(
        accessor='title',
        verbose_name=_('Title'),
        tooltip=TOOLTIP_TITLE,
    )
    wfs_featuretypes = MrMapColumn(
        verbose_name=_('Featuretypes'),
        empty_values=[], )
    wfs_status = MrMapColumn(
        verbose_name=_('Status'),
        empty_values=[False, ],
        tooltip=TOOLTIP_STATUS,
    )
    wfs_health = MrMapColumn(
        verbose_name=_('Health'),
        empty_values=[False, ],
        tooltip=TOOLTIP_HEALTH,
    )
    wfs_version = MrMapColumn(
        accessor='service.service_type.version',
        verbose_name=_('Version'),
        tooltip=TOOLTIP_VERSION,
    )
    wfs_data_provider = MrMapColumn(
        accessor='contact.organization_name',
        verbose_name=_('Data provider'),
        tooltip=TOOLTIP_DATA_PROVIDER,
    )
    wfs_registered_by_group = MrMapColumn(
        accessor='service.created_by',
        verbose_name=_('Registered by group'),
        tooltip=TOOLTIP_REGISTERED_BY_GROUP,
    )
    wfs_registered_for = MrMapColumn(
        accessor='service.published_for',
        verbose_name=_('Registered for'),
        tooltip=TOOLTIP_REGISTERED_FOR,
    )
    wfs_created_on = MrMapColumn(
        accessor='created',
        verbose_name=_('Created on'),
        tooltip=TOOLTIP_CREATED_ON,
    )
    wfs_actions = MrMapColumn(
        verbose_name=_('Actions'),
        empty_values=[],
        orderable=False,
        tooltip=TOOLTIP_ACTIONS,
        attrs={"td": {"style": "white-space:nowrap;"}}
    )

    def render_wfs_title(self, value, record):
        return self.get_link(tooltip=_(f'Click to open the detail view of <strong>{value}</strong>.'),
                             href=reverse('resource:detail', args=(record.id,)),
                             value=value,
                             permission=None)

    @staticmethod
    def render_wfs_featuretypes(record):
        count = record.service.featuretypes.count()
        return str(count)

    def render_wfs_status(self, record):
        return self.get_status_icons(record=record)

    def render_wfs_health(self, record):
        return self.get_health_icons(record=record)

    def render_wfs_data_provider(self, value, record):
        return self.get_link(tooltip=_(f'Click to open the detail view of <strong>{value}</strong>.'),
                             href=reverse('structure:detail-organization', args=(record.contact.id,)),
                             value=value,
                             permission=None)

    def render_wfs_registered_by_group(self, value, record):
        return self.get_link(tooltip=_(f'Click to open the detail view of <strong>{value}</strong>.'),
                             href=reverse('structure:detail-group', args=(record.service.created_by.id,)),
                             value=value,
                             permission=None)

    def render_wfs_registered_for(self, value, record):
        if record.service.published_for is not None:
            return self.get_link(tooltip=_(f'Click to open the detail view of <strong>{value}</strong>.'),
                                 href=reverse('structure:detail-organization', args=(record.service.published_for.id,)),
                                 value=value,
                                 permission=None)
        else:
            return value

    def render_wfs_actions(self, record):
        return _get_action_btns_for_service_table(self, record)

    @staticmethod
    def order_wfs_featuretypes(queryset, is_descending):
        queryset = queryset.annotate(
            count=Count("service__featuretypes")
        ).order_by(("-" if is_descending else "") + "count")
        return queryset, True

    def order_wfs_status(self, queryset, is_descending):
        return self.order_status(queryset=queryset, is_descending=is_descending)

    def order_wfs_health(self, queryset, is_descending):
        return self.order_health(queryset=queryset, is_descending=is_descending)


class CswTable(MrMapTable):
    csw_title = MrMapColumn(
        accessor='title',
        verbose_name=_('Title'),
        tooltip=TOOLTIP_TITLE,
    )
    csw_version = MrMapColumn(
        accessor='service.service_type.version',
        verbose_name=_('Version'),
        tooltip=TOOLTIP_VERSION,
    )
    csw_last_haverest = MrMapColumn(
        accessor='service',
        verbose_name=_('Last harvest'),
        tooltip=_('Timestamp of the last harvest'),
    )
    csw_collected_haverest_records = MrMapColumn(
        accessor='service',
        verbose_name=_('Collected harvest records'),
        tooltip=_('Count of all haverest records'),
    )
    csw_registered_by_group = MrMapColumn(
        accessor='service.created_by',
        verbose_name=_('Registered by group'),
        tooltip=TOOLTIP_REGISTERED_BY_GROUP,
    )
    csw_actions = MrMapColumn(
        verbose_name=_('Actions'),
        empty_values=[],
        orderable=False,
        tooltip=TOOLTIP_ACTIONS,
        attrs={"td": {"style": "white-space:nowrap;"}}
    )

    @staticmethod
    def render_csw_last_haverest(value, record):
        harvest_result = HarvestResult.objects.filter(
            service=value
        ).order_by(
            "-created"
        ).first()

        return harvest_result.timestamp_start if harvest_result is not None else None

    @staticmethod
    def render_csw_collected_haverest_records(value, record):
        harvest_result = HarvestResult.objects.filter(
            service=value
        ).order_by(
            "-created"
        ).first()
        return harvest_result.number_results if harvest_result is not None else None

    def render_csw_title(self, value, record):
        return self.get_link(tooltip=_(f'Click to open the detail view of <strong>{value}</strong>.'),
                             href=reverse('resource:detail', args=(record.id,)),
                             value=value,
                             permission=None)

    def render_csw_registered_by_group(self, value, record):
        return self.get_link(tooltip=_(f'Click to open the detail view of <strong>{value}</strong>.'),
                             href=reverse('structure:detail-group', args=(record.service.created_by.id,)),
                             value=value,
                             permission=None)

    def render_csw_actions(self, record):
        btns = ''
        btns += self.get_btn(
            href=reverse('resource:activate', args=(record.id,)) + f"?current-view={self.current_view}",
            btn_color=get_theme(self.user)["TABLE"]["BTN_WARNING_COLOR" if record.is_active else "BTN_SUCCESS_COLOR"],
            btn_value=get_theme(self.user)["ICONS"]["POWER_OFF"],
            permission=PermissionEnum.CAN_EDIT_METADATA,
            tooltip=format_html(_(
                f"{'Deactivate' if record.is_active else 'Activate'} resource <strong>{record.title} [{record.id}]</strong>"), ),
            tooltip_placement='left', )

        btns += self.get_btn(
            href=reverse('csw:harvest-catalogue', args=(record.id,)) + f"?current-view={self.current_view}",
            btn_color=get_theme(self.user)["TABLE"]["BTN_INFO_COLOR"],
            btn_value=get_theme(self.user)["ICONS"]["HARVEST"],
            permission=PermissionEnum.CAN_EDIT_METADATA,
            tooltip=format_html(_(
                f"Havest resource <strong>{record.title} [{record.id}]</strong>"), ),
            tooltip_placement='left', )

        btns += self.get_btn(
            href=reverse('resource:remove', args=(record.id,)) + f"?current-view={self.current_view}",
            btn_color=get_theme(self.user)["TABLE"]["BTN_DANGER_COLOR"],
            btn_value=get_theme(self.user)["ICONS"]['REMOVE'],
            permission=PermissionEnum.CAN_REMOVE_RESOURCE,
            tooltip=format_html(_(f"Remove <strong>{record.title} [{record.id}]</strong>"), ),
            tooltip_placement='left',
        )
        return format_html(btns)


class PendingTasksTable(MrMapTable):
    caption = _("Shows all currently running pending tasks.")
    pt_status = tables.Column(verbose_name=_('Status'), empty_values=[], orderable=False, attrs={"th": {"class": "col-sm-1"}})
    pt_service = tables.Column(verbose_name=_('Service'), empty_values=[], orderable=False, attrs={"th": {"class": "col-sm-3"}})
    pt_phase = tables.Column(verbose_name=_('Phase'), empty_values=[], orderable=False, attrs={"th": {"class": "col-sm-4"}})
    pt_progress = tables.Column(verbose_name=_('Progress'), empty_values=[], orderable=False, attrs={"th": {"class": "col-sm-3"}})
    pt_actions = tables.Column(verbose_name=_('Actions'), empty_values=[], orderable=False, attrs={"td": {"style": "white-space:nowrap;"}, "th": {"class": "col-sm-1"}})

    def render_pt_actions(self, record):
        btns = ''
        if record.type != PendingTaskEnum.REGISTER.value or record.error_report:
            btns += self.get_btn(href=reverse('structure:remove-task', args=(record.id,)),
                                 permission=None,
                                 tooltip=_('Delete this running task.'),
                                 btn_color=get_theme(self.user)["TABLE"]["BTN_DANGER_COLOR"],
                                 btn_value=get_theme(self.user)["ICONS"]['WINDOW_CLOSE'], )
        if record.error_report:
            btns += self.get_btn(href=reverse('structure:generate-error-report', args=(record.error_report.id,)),
                                 permission=None,
                                 tooltip=_('Download the error report as text file.'),
                                 btn_color=get_theme(self.user)["TABLE"]["BTN_WARNING_COLOR"],
                                 btn_value=get_theme(self.user)["ICONS"]['CSW'],)
        return format_html(btns)

    def render_pt_status(self, record):
        json_description = json.loads(record.description)
        if 'ERROR' in json_description.get('phase', ""):
            return self.get_icon(icon=get_theme(self.user)["ICONS"]['ERROR'],
                                 icon_color='text-danger',
                                 tooltip='This task stopped with error.')
        else:
            return self.get_icon(icon=get_theme(self.user)["ICONS"]['PLAY'],
                                 icon_color='text-success',
                                 tooltip='This task is still running.')

    @staticmethod
    def render_pt_service(record):
        # TODO: remove this sticky json
        return str(json.loads(record.description).get('service', "resource_name_missing")) if 'service' in json.loads(record.description) else _('unknown')

    @staticmethod
    def render_pt_phase(record):
        # TODO: remove this sticky json
        return str(json.loads(record.description).get('phase', "phase_information_missing")) if 'phase' in json.loads(record.description) else _('unknown')

    @staticmethod
    def render_pt_progress(record):
        progress = record.progress or 0
        progress = str(int(progress))
        try:
            return format_html('<div class="progress">' \
                               '<div class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar" ' \
                               'aria-valuenow="' + progress + '" aria-valuemin="0" aria-valuemax="100" ' \
                                                                    'style="width: ' + progress + '%">'+ progress + \
                                                                                                        ' %</div>' \
                                                                                                        '</div>')
        except Exception as e:
            return str(e)


class ChildLayerTable(MrMapTable):
    id = tables.Column(visible=False)
    title = tables.Column(visible=False)
    child_layer_title = tables.Column(empty_values=[], order_by='title', )

    caption = _("Shows all child layer of current WMS.")

    @staticmethod
    def render_child_layer_title(record):
        url = reverse('resource:get-metadata-html', args=(record['id'],))

        if record['sublayers_count'] > 0:
            return format_html("<a href='{}'>{} <span class='badge badge-secondary'>{}</span></a>",
                               url,
                               record['title'],
                               record['sublayers_count'])
        else:
            return format_html("<a href='{}'>{}</a>",
                               url,
                               record['title'], )


class FeatureTypeTable(MrMapTable):
    id = tables.Column(visible=False)
    title = tables.Column(visible=False)
    featuretype_title = tables.Column(empty_values=[], order_by='title', )

    caption = _("Shows all featuretypes of current WFS.")

    @staticmethod
    def render_featuretype_title(record):
        url = reverse('resource:get-metadata-html', args=(record['id'],))

        return format_html("<a href='{}'>{}</a>",
                           url,
                           record['title'], )


class CoupledMetadataTable(MrMapTable):
    id = tables.Column(visible=False)
    title = tables.Column(visible=False)
    coupled_metadata_title = tables.Column(empty_values=[], order_by='title', )

    caption = _("Shows all coupled metadata of current service.")

    @staticmethod
    def render_coupled_metadata_title(record):
        url = reverse('resource:get-metadata-html', args=(record['id'],))

        return format_html("<a href='{}'>{}</a>",
                           url,
                           record['title'], )


class UpdateServiceElements(MrMapTable):
    title = tables.Column(empty_values=[],)
    identifier = tables.Column(empty_values=[],)


class ProxyLogTable(MrMapTable):
    caption = _("Shows all logs for a service.")

    class Meta:
        row_attrs = {
            "class": "text-center"
        }
    metadata_id = MrMapColumn(
        accessor='metadata.id',
        verbose_name=_('Service ID'),
        tooltip=_("The title of the related service")
    )
    metadata_title = MrMapColumn(
        accessor='metadata.title',
        verbose_name=_('Service Title'),
        tooltip=_("The title of the related service")
    )
    user_name = MrMapColumn(
        accessor='user',
        verbose_name=_('User'),
        tooltip=_("Name of the user which produced this log entry")
    )
    timestamp = MrMapColumn(
        accessor='timestamp',
        verbose_name=_('Timestamp'),
        tooltip=_("Timestamp when the entry was produced")
    )
    operation = MrMapColumn(
        accessor='operation',
        tooltip=_("Operation param of the request"),
        verbose_name=_('Operation'),
    )
    megapixel = MrMapColumn(
        accessor='response_wms_megapixel',
        tooltip=_("Delivered megapixel of map material"),
        verbose_name=_('Response megapixel'),
    )
    features = MrMapColumn(
        accessor='response_wfs_num_features',
        tooltip=_("Delivered number of features"),
        verbose_name=_('Response features'),
    )

    def fill_csv_response(self, stream):
        csv_writer = csv.writer(stream)
        csv_writer.writerow([
            _("ID"),
            _("Title"),
            _("User"),
            _("Operation"),
            _("Delivered Features (WFS)"),
            _("Delivered Megapixel (WMS)"),
            _("Timestamp"),
        ])
        for log in self.data.data:
            csv_writer.writerow(
                [
                    log.metadata.id,
                    log.metadata.title,
                    log.user,
                    log.operation,
                    log.response_wfs_num_features,
                    log.response_wms_megapixel,
                    log.timestamp,
                ]
            )
        return stream.getvalue()


class DatasetTable(MrMapTable):
    caption = _("Shows all datasets which are configured in your Mr. Map environment. You can Edit them if you want.")

    dataset_title = MrMapColumn(
        accessor='title',
        verbose_name=_('Title'),
        tooltip=TOOLTIP_TITLE,
    )
    dataset_related_objects = MrMapColumn(
        verbose_name=_('Related objects'),
        empty_values=[],
        tooltip=_('The related service from which this dataset is referenced'),)
    dataset_origins = MrMapColumn(
        verbose_name=_('Origins'),
        empty_values=[],
        tooltip=_('How the resource got into the system.'))
    dataset_actions = MrMapColumn(
        verbose_name=_('Actions'),
        empty_values=[],
        orderable=False,
        tooltip=TOOLTIP_ACTIONS,
        attrs={"td": {"style": "white-space:nowrap;"}})

    def render_dataset_title(self, value, record):
        return self.get_link(tooltip=_(f'Click to open the html view of dataset <strong>{value}</strong>'),
                             href=reverse('resource:get-metadata-html', args=(record.id,)),
                             value=value,
                             permission=None,
                             open_in_new_tab=True,)

    def render_dataset_related_objects(self, record):
        related_metadatas = Metadata.objects.filter(
            related_metadata__metadata_to=record
        ).prefetch_related(
            "related_metadata"
        )
        link_list = []
        for metadata in related_metadatas:
            link = self.get_link(tooltip=_(f'Click to open the detail view of related service <strong>{metadata.title} [{metadata.id}]"</strong>'),
                                 href=reverse('resource:detail', args=(metadata.id,)),
                                 value=f"{metadata.title} [{metadata.id}]",
                                 permission=None,)
            link_list.append(link, )
        return format_html(', '.join(link_list))

    def render_dataset_origins(self, record):
        related_metadatas = MetadataRelation.objects.filter(
            metadata_to=record
        )
        origin_list = []
        rel_mds = list(record.related_metadata.all())
        relations = list(related_metadatas) + rel_mds
        for relation in relations:
            origin_list.append(f"{relation.origin}")

        return format_html(', '.join(origin_list))

    def render_dataset_actions(self, record):
        is_mr_map_origin = not MetadataRelation.objects.filter(
            metadata_to=record
        ).exclude(
            origin=ResourceOriginEnum.EDITOR.value
        ).exists()

        btns = ''
        btns += self.get_btn(href=reverse('editor:dataset-metadata-wizard-instance', args=(record.id,))+f"?current-view={self.current_view}",
                             permission=PermissionEnum.CAN_EDIT_METADATA,
                             tooltip=format_html(_(f"Edit <strong>{record.title} [{record.id}]</strong> dataset")),
                             tooltip_placement='left',
                             btn_color=get_theme(self.user)["TABLE"]["BTN_WARNING_COLOR"],
                             btn_value=get_theme(self.user)["ICONS"]['EDIT'],)

        btns += self.get_btn(href=reverse('editor:restore-dataset-metadata', args=(record.id,))+f"?current-view={self.current_view}",
                             permission=PermissionEnum.CAN_EDIT_METADATA,
                             tooltip=format_html(_(f"Restore <strong>{record.title} [{record.id}]</strong> dataset")),
                             tooltip_placement='left',
                             btn_color=get_theme(self.user)["TABLE"]["BTN_DANGER_COLOR"],
                             btn_value=get_theme(self.user)["ICONS"]['UNDO'],
                             ) if not is_mr_map_origin else ''

        btns += self.get_btn(href=reverse('editor:remove-dataset-metadata', args=(record.id,))+f"?current-view={self.current_view}",
                             permission=PermissionEnum.CAN_REMOVE_DATASET_METADATA,
                             tooltip=format_html(_(f"Remove <strong>{record.title} [{record.id}]</strong> dataset"), ),
                             tooltip_placement='left',
                             btn_color=get_theme(self.user)["TABLE"]["BTN_DANGER_COLOR"],
                             btn_value=get_theme(self.user)["ICONS"]['REMOVE'],
                             ) if is_mr_map_origin else ''

        return format_html(btns)