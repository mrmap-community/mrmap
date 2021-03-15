from django.contrib.gis.geos import MultiPolygon, GEOSGeometry
from django.forms import DateTimeInput, DateInput, Textarea
from MrMap.settings import DEFAULT_DATE_TIME_FORMAT
from service.settings import DEFAULT_SERVICE_BOUNDING_BOX
from django_filters.widgets import SuffixedMultiWidget


GEOMAN_CONTROLS = {'position': '\'topright\'',
                   'drawCircle': 'false',
                   'drawCircleMarker': 'false',
                   'drawPolyline': 'false',
                   'drawRectangle': 'true',
                   'drawMarker': 'false',
                   'removalMode': 'true',
                   'cutPolygon': 'false', }


class BootstrapDatePickerInput(DateInput):
    template_name = 'widgets/bootstrap_datepicker.html'

    def get_context(self, name, value, attrs):
        datetimepicker_id = 'datetimepicker_{name}'.format(name=name)
        if attrs is None:
            attrs = dict()
        attrs['data-target'] = '#{id}'.format(id=datetimepicker_id)
        attrs['data-toggle'] = 'datetimepicker'

        if 'class' in attrs:
            classes = attrs['class'].split()
            if 'form-control' not in classes:
                classes.append('form-control')
            classes.append('datetimepicker-input')
            attrs['class'] = " ".join(classes)
        else:
            attrs['class'] = 'form-control datetimepicker-input'

        context = super().get_context(name, value, attrs)
        context['widget']['datetimepicker_id'] = datetimepicker_id
        return context


class BootstrapDateTimePickerInput(DateTimeInput):
    template_name = 'widgets/bootstrap_datepicker.html'

    def get_context(self, name, value, attrs):
        datetimepicker_id = 'datetimepicker_{name}'.format(name=name)
        datetime_format = attrs.get("format", DEFAULT_DATE_TIME_FORMAT)
        if attrs is None:
            attrs = dict()
        attrs['data-target'] = '#{id}'.format(id=datetimepicker_id)
        attrs['data-toggle'] = 'datetimepicker'

        if 'class' in attrs:
            classes = attrs['class'].split()
            if 'form-control' not in classes:
                classes.append('form-control')
            classes.append('datetimepicker-input')
            attrs['class'] = " ".join(classes)
        else:
            attrs['class'] = 'form-control datetimepicker-input'

        context = super().get_context(name, value, attrs)
        context['widget']['datetimepicker_id'] = datetimepicker_id
        context['widget']['datetimepicker_format'] = datetime_format
        return context


class BootstrapDatePickerRangeWidget(SuffixedMultiWidget):
    template_name = 'django_filters/widgets/multiwidget.html'
    suffixes = ['min', 'max']

    def __init__(self, format: str = 'YYYY-MM-DD', attrs={}):
        widgets = (BootstrapDateTimePickerInput, BootstrapDateTimePickerInput)
        attrs["format"] = format
        super().__init__(widgets, attrs)

    def decompress(self, value):
        if value:
            return [value.start, value.stop]
        return [None, None]


class LeafletGeometryInput(Textarea):
    template_name = 'widgets/leaflet_geometry_input.html'
    bbox = DEFAULT_SERVICE_BOUNDING_BOX
    geoman_controls = None

    def __init__(self,
                 request=None,
                 activate_download=True,
                 activate_upload=True,
                 geoman_controls=None,
                 *args,
                 **kwargs):
        super(LeafletGeometryInput, self).__init__(*args, **kwargs)
        self.request = request
        self.activate_download = activate_download
        self.activate_upload = activate_upload
        self.geoman_controls = geoman_controls if geoman_controls else GEOMAN_CONTROLS

    def get_context(self,
                    name,
                    value,
                    attrs):
        if 'id' in attrs:
            attrs['id'] = attrs['id'].replace(" ", "_").replace("-","_")
        leaflet_geometry_input_id = f'leaflet_geometry_input_id_{attrs["id"]}'
        if attrs is None:
            attrs = dict()
        # attrs['data-target'] = f'#{leaflet_geometry_input_id}'
        # attrs['readonly'] = ''

        if 'class' in attrs:
            classes = attrs['class'].split()
            if 'form-control' not in classes:
                classes.append('form-control')
            classes.append('leaflet-geometry-input')
            attrs['class'] = " ".join(classes)
        else:
            attrs['class'] = 'form-control leaflet-geometry-input'

        context = super().get_context(name, value, attrs)
        context['widget']['leaflet_geometry_input_id'] = leaflet_geometry_input_id
        context['bbox'] = self.bbox

        if value:
            context['geojson'] = value.geojson if isinstance(value, MultiPolygon) else GEOSGeometry(value).geojson

        context['activate_download'] = self.activate_download
        context['activate_upload'] = self.activate_upload
        context['geoman_controls'] = self.geoman_controls
        return context
