from django import forms
from django.utils.translation import gettext_lazy as _
from django_filters import BaseInFilter, FilterSet
from django_filters.filters import CharFilter
from notify.enums import ProcessStatusEnum
from notify.models import BackgroundProcess


class ProcessStatusForm(forms.CharField):
    """Form field which accepts a status of a background process by its name."""

    default_error_messages = {
        'invalid_choice': _('Select a valid status of a background process.'),
    }

    def to_python(self, value):
        value = super().to_python(value)
        if value in self.empty_values:
            return None
        if value.isdigit():
            # the status is stored as a number, so a client which reads the
            # database instead of the api may also send it
            status = ProcessStatusEnum(
                int(value)) if int(value) in ProcessStatusEnum.values else None
        else:
            status = ProcessStatusEnum(value)
        if status is None:
            raise forms.ValidationError(
                self.error_messages['invalid_choice'], code='invalid_choice')
        return status.value


class ProcessStatusFilter(BaseInFilter, CharFilter):
    """Filter which accepts one or more statuses of a background process.

    The api answers the status of a process by the name of its choice, so the
    values of this filter are the names of ProcessStatusEnum and not the
    numbers the database stores.
    """
    field_class = ProcessStatusForm


class BackgroundProcessFilterSet(FilterSet):
    status = ProcessStatusFilter(
        label=_('status'),
        field_name='status',
        help_text=_('Multiple values may be separated by commas.'))

    class Meta:
        model = BackgroundProcess
        fields = {
            'id': ['exact', 'icontains', 'contains', 'in'],
            "process_type": ["exact", "icontains", "contains"],
            "description": ["exact", "icontains", "contains"],
            "phase": ["exact", "icontains", "contains"],
        }
