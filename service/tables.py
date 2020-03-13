import django_tables2 as tables
from django.db.models.functions import Length
from django.utils.html import format_html
from django.urls import reverse
import json
from MapSkinner.celery_app import app
from celery.result import AsyncResult
from MapSkinner.utils import get_theme, get_ok_nok_icon
from MapSkinner.consts import URL_PATTERN, URL_BTN_PATTERN, BTN_CLASS, BTN_SM_CLASS
from django.db.models import Count
from django.utils.translation import gettext_lazy as _


def _get_close_button(url, user):
    return format_html(URL_BTN_PATTERN,
                       BTN_CLASS,
                       BTN_SM_CLASS,
                       get_theme(user)["TABLE"]["BTN_DANGER_COLOR"],
                       url,
                       format_html(get_theme(user)["ICONS"]['WINDOW_CLOSE']),)


class ServiceTable(tables.Table):
    attrs = {
        "th": {
            "class": "align-middle",
        }
    }
    wms_title = tables.Column(accessor='title', verbose_name='Title', empty_values=[], attrs=attrs)
    wms_active = tables.Column(accessor='is_active', verbose_name='Active', attrs=attrs)
    wms_secured_access = tables.Column(accessor='is_secured', verbose_name='Secured access', attrs=attrs)
    wms_secured_externally = tables.Column(accessor='external_authentication', verbose_name='Secured externally', empty_values=[False,], attrs=attrs)
    wms_version = tables.Column(accessor='service.servicetype.version', verbose_name='Version', attrs=attrs)
    wms_data_provider = tables.Column(accessor='contact.organization_name', verbose_name='Data provider', attrs=attrs)
    wms_registered_by_group = tables.Column(accessor='service.created_by', verbose_name='Registered by group', attrs=attrs)
    wms_registered_for = tables.Column(accessor='service.published_for', verbose_name='Registered for', attrs=attrs)
    wms_created_on = tables.Column(accessor='created', verbose_name='Created on', attrs=attrs)

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
    caption = _("Shows all WMS which are configured in your Mr. Map environment.")

    attrs = {
        "th": {
            "class": "align-middle",
        }
    }
    wms_layers = tables.Column(verbose_name='Layers', empty_values=[], attrs=attrs)

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


class WmsLayerTable(ServiceTable):
    wms_parent_service = tables.Column(verbose_name='Parent service', empty_values=[], )

    caption = _("Shows all WMS sublayers which are configured in your Mr. Map environment.")

    class Meta:
        sequence = ("wms_title", "wms_parent_service", "...")
        row_attrs = {
            "class": "text-center"
        }

    def render_wms_parent_service(self, record):
        url = reverse('service:detail', args=(record.service.parent_service.metadata.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, record.service.parent_service.metadata.title)

    @staticmethod
    def order_wms_parent_service(queryset, is_descending):
        queryset = queryset.annotate(
            title_length=Length("service__parent_service__metadata__title")
        ).order_by(("-" if is_descending else "") + "title_length")
        return queryset, True


class WfsServiceTable(tables.Table):
    caption = _("Shows all WFS which are configured in your Mr. Map environment.")

    class Meta:
        row_attrs = {
            "class": "text-center"
        }

    wfs_title = tables.Column(accessor='title', verbose_name='Title', )
    wfs_featuretypes = tables.Column(verbose_name='Featuretypes', empty_values=[], )
    wfs_active = tables.Column(accessor='is_active', verbose_name='Active', )
    wfs_secured_access = tables.Column(accessor='is_secured', verbose_name='Secured access', )
    wfs_secured_externally = tables.Column(accessor='external_authentication', verbose_name='Secured externally', empty_values=[False,], )
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
        count = record.service.featuretypes.count()
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

    @staticmethod
    def order_wfs_featuretypes(queryset, is_descending):
        queryset = queryset.annotate(
            count=Count("service__featuretypes")
        ).order_by(("-" if is_descending else "") + "count")
        return queryset, True


class PendingTasksTable(tables.Table):
    caption = _("Shows all currently running pending tasks.")

    pt_cancle = tables.Column(verbose_name=' ', empty_values=[], orderable=False, )
    pt_status = tables.Column(verbose_name='Status', empty_values=[], orderable=False, )
    pt_service = tables.Column(verbose_name='Service', empty_values=[], orderable=False,)
    pt_phase = tables.Column(verbose_name='Phase', empty_values=[], orderable=False,)
    pt_progress = tables.Column(verbose_name='Progress', empty_values=[], orderable=False,)

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


class ChildLayerTable(tables.Table):
    id = tables.Column(visible=False)
    title = tables.Column(visible=False)
    child_layer_title = tables.Column(empty_values=[], order_by='title', )

    caption = _("Shows all child layer of current WMS.")

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)

    @staticmethod
    def render_child_layer_title(record):
        url = reverse('service:get-metadata-html', args=(record['id'],))

        if record['sublayers_count'] > 0:
            return format_html("<a href='{}'>{} <span class='badge badge-secondary'>{}</span></a>",
                               url,
                               record['title'],
                               record['sublayers_count'])
        else:
            return format_html("<a href='{}'>{}</a>",
                               url,
                               record['title'], )


class FeatureTypeTable(tables.Table):
    id = tables.Column(visible=False)
    title = tables.Column(visible=False)
    featuretype_title = tables.Column(empty_values=[], order_by='title', )

    caption = _("Shows all featuretypes of current WFS.")

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)

    @staticmethod
    def render_featuretype_title(record):
        url = reverse('service:get-metadata-html', args=(record['id'],))

        return format_html("<a href='{}'>{}</a>",
                           url,
                           record['title'], )


class CoupledMetadataTable(tables.Table):
    id = tables.Column(visible=False)
    title = tables.Column(visible=False)
    coupled_metadata_title = tables.Column(empty_values=[], order_by='title', )

    caption = _("Shows all coupled metadata of current service.")

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)

    @staticmethod
    def render_coupled_metadata_title(record):
        url = reverse('service:get-metadata-html', args=(record['id'],))

        return format_html("<a href='{}'>{}</a>",
                           url,
                           record['title'], )