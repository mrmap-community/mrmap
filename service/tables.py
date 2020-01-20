import django_tables2 as tables
from django.utils.html import format_html
from django.urls import reverse

class ChildLayerTable(tables.Table):
    id = tables.Column(visible=False)
    title = tables.Column(visible=False)
    child_layer_title = tables.Column(empty_values=[], order_by='title',)

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
                               record['title'],)
