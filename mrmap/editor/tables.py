from django.utils.safestring import mark_safe
import django_tables2 as tables
from leaflet.forms.fields import GeometryField
from leaflet.forms.widgets import LeafletWidget
from service.models import AllowedOperation


class AllowedOperationTable(tables.Table):
    class Meta:
        model = AllowedOperation
        fields = ('operations', 'allowed_groups', 'root_metadata', 'allowed_area')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'allowed-operations-table'

    def render_allowed_area(self, record, value):
        leaflet_widget = LeafletWidget()
        leaflet_widget.modifiable = False
        leaflet_field = GeometryField(widget=leaflet_widget)
        field_name = f'id-{record.id}-allowed_area'
        field_value = value.geojson
        leaflet_field_html = leaflet_field.widget.render(field_name, field_value)
        # todo: nest the leaflet client in a accordion. We need to customize the init call to the shown event of the
        #  accordion
        return mark_safe(leaflet_field_html)
