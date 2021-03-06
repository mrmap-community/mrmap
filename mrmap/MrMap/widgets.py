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
