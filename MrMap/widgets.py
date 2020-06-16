from django.forms import DateTimeInput, DateInput, TextInput, Textarea

from MrMap.utils import get_theme
from service.settings import DEFAULT_SERVICE_BOUNDING_BOX
from users.helper import user_helper
from django.utils.translation import gettext_lazy as _


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


class LeafletGeometryInput(Textarea):
    template_name = 'widgets/leaflet_geometry_input.html'

    def __init__(self,
                 bbox=None,
                 geojson=None,
                 request=None,
                 activate_download=True,
                 activate_upload=True,
                 *args,
                 **kwargs):
        super(LeafletGeometryInput, self).__init__(*args, **kwargs)
        self.bbox = bbox or DEFAULT_SERVICE_BOUNDING_BOX
        self.geojson = geojson
        self.request = request
        self.activate_download = activate_download
        self.activate_upload = activate_upload

    def get_context(self,
                    name,
                    value,
                    attrs):
        if 'id' in attrs:
            attrs['id'] = attrs['id'].replace(" ", "_").replace("-","_")
        leaflet_geometry_input_id = f'leaflet_geometry_input_id_{attrs["id"]}'
        if attrs is None:
            attrs = dict()
        attrs['data-target'] = f'#{leaflet_geometry_input_id}'
        attrs['readonly'] = ''

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
        context['geojson'] = self.geojson
        context['THEME'] = get_theme(user_helper.get_user(request=self.request))
        context['activate_download'] = self.activate_download
        context['activate_upload'] = self.activate_upload
        return context
