import django_tables2 as tables
from django.utils.html import format_html
from django.urls import reverse
import json
from MapSkinner.celery_app import app
from celery.result import AsyncResult
from MapSkinner.utils import get_theme, get_ok_nok_icon
from MapSkinner.consts import URL_PATTERN, URL_BTN_PATTERN, BTN_CLASS, BTN_SM_CLASS


def _get_close_button(url, user):
    return format_html(URL_BTN_PATTERN,
                       BTN_CLASS,
                       BTN_SM_CLASS,
                       get_theme(user)["TABLE"]["BTN_DANGER_COLOR"],
                       url,
                       format_html(get_theme(user)["ICONS"]['WINDOW_CLOSE']),)


class ServiceTable(tables.Table):
    wms_title = tables.Column(accessor='title', verbose_name='Title', empty_values=[])
    wms_active = tables.Column(accessor='is_active', verbose_name='Active', )
    wms_secured_access = tables.Column(accessor='is_secured', verbose_name='Secured access', )
    wms_secured_externally = tables.Column(accessor='has_external_authentication', verbose_name='Secured externally', )
    wms_version = tables.Column(accessor='service.servicetype.version', verbose_name='Version', )
    wms_data_provider = tables.Column(accessor='contact.organization_name', verbose_name='Data provider', )
    wms_registered_by_group = tables.Column(accessor='service.created_by', verbose_name='Registered by group', )
    wms_registered_for = tables.Column(accessor='service.published_for', verbose_name='Registered for', )
    wms_created_on = tables.Column(accessor='created', verbose_name='Created on', )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)

    def render_wms_title(self, value, record):
        url = reverse('service:detail', args=(record.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )

    @staticmethod
    def render_wms_active(value):
        return get_ok_nok_icon(value)

    @staticmethod
    def render_wms_secured_access(value):
        return get_ok_nok_icon(value)

    @staticmethod
    def render_wms_secured_externally(value):
        return get_ok_nok_icon(value)

    def render_wms_data_provider(self, value, record):
        url = reverse('structure:detail-organization', args=(record.contact.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )

    def render_wms_registered_by_group(self, value, record):
        url = reverse('structure:detail-group', args=(record.service.created_by.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )

    def render_wms_registered_for(self, value, record):
        if record.service.published_for is not None:
            url = reverse('structure:detail-organization', args=(record.service.published_for.id,))
            return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )
        else:
            return value


class WmsServiceTable(ServiceTable):
    wms_layers = tables.Column(verbose_name='Layers', empty_values=[], )

    class Meta:
        sequence = ("wms_title", "wms_layers", "...")

    @staticmethod
    def render_wms_layers(record):
        count = len(record.service.child_service.all())
        return str(count)


class WmsLayerTable(ServiceTable):
    wms_parent_service = tables.Column(verbose_name='Parent service', empty_values=[], )

    class Meta:
        sequence = ("wms_title", "wms_parent_service", "...")

    def render_wms_parent_service(self, record):
        url = reverse('service:detail', args=(record.service.parent_service.metadata.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, record.service.parent_service.metadata.title)


class WfsServiceTable(tables.Table):
    wfs_title = tables.Column(accessor='title', verbose_name='Title', )
    wfs_featuretypes = tables.Column(verbose_name='Featuretypes', empty_values=[], )
    wfs_active = tables.Column(accessor='is_active', verbose_name='Active', )
    wfs_secured_access = tables.Column(accessor='is_secured', verbose_name='Secured access', )
    wfs_secured_externally = tables.Column(accessor='has_external_authentication', verbose_name='Secured externally', )
    wfs_version = tables.Column(accessor='service.servicetype.version', verbose_name='Version', )
    wfs_data_provider = tables.Column(accessor='contact.organization_name', verbose_name='Data provider', )
    wfs_registered_by_group = tables.Column(accessor='service.created_by', verbose_name='Registered by group', )
    wfs_registered_for = tables.Column(accessor='service.published_for', verbose_name='Registered for', )
    wfs_created_on = tables.Column(accessor='created', verbose_name='Created on', )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)

    def render_wfs_title(self, value, record):
        url = reverse('service:detail', args=(record.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )

    @staticmethod
    def render_wfs_featuretypes(record):
        count = len(record.service.featuretypes.all())
        return str(count)

    @staticmethod
    def render_wfs_active(value):
        return get_ok_nok_icon(value)

    @staticmethod
    def render_wfs_active(value):
        return get_ok_nok_icon(value)

    @staticmethod
    def render_wfs_secured_access(value):
        return get_ok_nok_icon(value)

    @staticmethod
    def render_wfs_secured_externally(value):
        return get_ok_nok_icon(value)

    def render_wfs_data_provider(self, value, record):
        url = reverse('structure:detail-organization', args=(record.contact.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )

    def render_wfs_registered_by_group(self, value, record):
        url = reverse('structure:detail-group', args=(record.service.created_by.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )

    def render_wfs_registered_for(self, value, record):
        if record.service.published_for is not None:
            url = reverse('structure:detail-organization', args=(record.service.published_for.id,))
            return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )
        else:
            return value


class PendingTasksTable(tables.Table):
    pt_cancle = tables.Column(verbose_name=' ', empty_values=[], )
    pt_status = tables.Column(verbose_name='Status', empty_values=[], )
    pt_service = tables.Column(verbose_name='Service', empty_values=[], )
    pt_phase = tables.Column(verbose_name='Phase', empty_values=[], )
    pt_progress = tables.Column(verbose_name='Progress', empty_values=[], )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)

    def render_pt_cancle(self, record):
        url = reverse('structure:remove-task', args=(record.task_id,))
        return _get_close_button(url, self.user)

    @staticmethod
    def render_pt_status():
        return format_html('<div class="spinner-border spinner-border-sm" role="status">'
                           '<span class="sr-only">Loading...</span>'
                           '</div>')

    @staticmethod
    def render_pt_service(record):
        # TODO: remove this sticky json
        return str(json.loads(record.description)['service'])

    @staticmethod
    def render_pt_phase(record):
        # TODO: remove this sticky json
        try:
            return str(json.loads(record.description)['phase'])
        except KeyError as e:
            return str(e)

    @staticmethod
    def render_pt_progress(record):

        task = AsyncResult(record.task_id, app=app)
        try:
            info_dict = task.info

            if info_dict is not None:
                if task.info['current'] is None:
                    progress_value = '1'  # 1 % to show something ¯\_(ツ)_/¯
                else:
                    progress_value = str(int(task.info['current']))
            else:
                progress_value = '1' # 1 % to show something ¯\_(ツ)_/¯

            return format_html('<div class="progress">' \
                               '<div class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar" ' \
                               'aria-valuenow="' + progress_value + '" aria-valuemin="0" aria-valuemax="100" ' \
                                                                    'style="width: ' + progress_value + '%">'+ progress_value + \
                                                                                                        ' %</div>' \
                                                                                                        '</div>')
        except Exception as e:
            return str(e)
