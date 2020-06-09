from django.forms import DateTimeInput, DateInput


class BootstrapDatePickerInput(DateInput):
    template_name = 'widgets/bootstrap_datepicker.html'

    def get_context(self, name, value, attrs):
        datetimepicker_id = 'datetimepicker_{name}'.format(name=name)
        if attrs is None:
            attrs = dict()
        attrs['data-target'] = '#{id}'.format(id=datetimepicker_id)

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
