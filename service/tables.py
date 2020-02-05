import django_tables2 as tables
from django.utils.html import format_html
from django.urls import reverse

URL_PATTERN = "<a href='{}'>{}</a>"


def _get_icon(self):
    if not self:
        return format_html("<i class='fas fa-check text-success'></i>")
    else:
        return format_html("<i class='fas fa-times text-danger'></i>")


class ServiceTable(tables.Table):
    wms_title = tables.Column(accessor='title', verbose_name='Title', )
    wms_active = tables.Column(accessor='is_active', verbose_name='Active', )
    wms_secured_access = tables.Column(accessor='is_secured', verbose_name='Secured access', )
    wms_secured_externally = tables.Column(accessor='has_external_authentication', verbose_name='Secured externally', )
    wms_version = tables.Column(accessor='service.servicetype.version', verbose_name='Version', )
    wms_data_provider = tables.Column(accessor='contact.organization_name', verbose_name='Data provider', )
    wms_registered_by_group = tables.Column(accessor='service.created_by', verbose_name='Registered by group', )
    wms_registered_for = tables.Column(accessor='service.published_for', verbose_name='Registered for', )
    wms_created_on = tables.Column(accessor='created', verbose_name='Created on', )

    @staticmethod
    def render_wms_title(value, record):
        url = reverse('service:detail', args=(record.id,))
        return format_html(URL_PATTERN, url, value, )

    @staticmethod
    def render_wms_active(value):
        return _get_icon(value)

    @staticmethod
    def render_wms_secured_access(value):
        return _get_icon(value)

    @staticmethod
    def render_wms_secured_externally(value):
        return _get_icon(value)

    @staticmethod
    def render_wms_data_provider(value, record):
        url = reverse('structure:detail-organization', args=(record.contact.id,))
        return format_html(URL_PATTERN, url, value, )

    @staticmethod
    def render_wms_registered_by_group(value, record):
        url = reverse('structure:detail-group', args=(record.service.created_by.id,))
        return format_html(URL_PATTERN, url, value, )

    @staticmethod
    def render_wms_registered_for(value, record):
        if record.service.published_for is not None:
            url = reverse('structure:detail-organization', args=(record.service.published_for.id,))
            return format_html(URL_PATTERN, url, value, )
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

    @staticmethod
    def render_wms_parent_service(record):
        url = reverse('service:detail', args=(record.service.parent_service.metadata.id,))
        return format_html(URL_PATTERN, url, record.service.parent_service.metadata.title)


class WfsServiceTable(tables.Table):
    wfs_title = tables.Column(accessor='title', verbose_name='Title', )
    wfs_featuretypes = tables.Column(verbose_name='Featuretypes', empty_values=[],)
    wfs_active = tables.Column(accessor='is_active', verbose_name='Active', )
    wfs_secured_access = tables.Column(accessor='is_secured', verbose_name='Secured access', )
    wfs_secured_externally = tables.Column(accessor='has_external_authentication', verbose_name='Secured externally', )
    wfs_version = tables.Column(accessor='service.servicetype.version', verbose_name='Version', )
    wfs_data_provider = tables.Column(accessor='contact.organization_name', verbose_name='Data provider', )
    wfs_registered_by_group = tables.Column(accessor='service.created_by', verbose_name='Registered by group', )
    wfs_registered_for = tables.Column(accessor='service.published_for', verbose_name='Registered for', )
    wfs_created_on = tables.Column(accessor='created', verbose_name='Created on', )

    @staticmethod
    def render_wfs_title(value, record):
        url = reverse('service:detail', args=(record.id,))
        return format_html(URL_PATTERN, url, value, )

    @staticmethod
    def render_wfs_featuretypes(record):
        count = len(record.service.featuretypes.all())
        return str(count)

    @staticmethod
    def render_wfs_active(value):
        return _get_icon(value)

    @staticmethod
    def render_wfs_active(value):
        return _get_icon(value)

    @staticmethod
    def render_wfs_secured_access(value):
        return _get_icon(value)

    @staticmethod
    def render_wfs_secured_externally(value):
        return _get_icon(value)

    @staticmethod
    def render_wfs_data_provider(value, record):
        url = reverse('structure:detail-organization', args=(record.contact.id,))
        return format_html(URL_PATTERN, url, value, )

    @staticmethod
    def render_wfs_registered_by_group(value, record):
        url = reverse('structure:detail-group', args=(record.service.created_by.id,))
        return format_html(URL_PATTERN, url, value, )

    @staticmethod
    def render_wfs_registered_for(value, record):
        if record.service.published_for is not None:
            url = reverse('structure:detail-organization', args=(record.service.published_for.id,))
            return format_html(URL_PATTERN, url, value, )
        else:
            return value