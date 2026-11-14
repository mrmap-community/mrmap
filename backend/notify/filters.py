from django import forms
from django.utils.translation import gettext_lazy as _
from django_filters import BaseInFilter, FilterSet
from django_filters.filters import CharFilter, UUIDFilter
from notify.enums import OperationStateEnum, ProcessStatusEnum
from notify.models import BackgroundProcess, OperationalIncident


#: the help of every filter of this api which takes more than one value in one
#: parameter: the same question is answered the same way, in one string
MULTIPLE_VALUES = _('Multiple values may be separated by commas.')


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


class OperationStateForm(forms.CharField):
    """Form field which accepts a normalized state by its name."""

    default_error_messages = {
        'invalid_choice': _('Select a valid state of a background operation.'),
    }

    def to_python(self, value):
        value = super().to_python(value)
        if value in self.empty_values:
            return None
        state = OperationStateEnum(
            value) if value in OperationStateEnum.values else None
        if state is None:
            raise forms.ValidationError(
                self.error_messages['invalid_choice'], code='invalid_choice')
        return state.value


class OperationStateFilter(BaseInFilter, CharFilter):
    """Filter which accepts one or more normalized states of an operation.

    The state of a process is derived from its stored fields, so the tabs of
    the background job center ask for the states they render and not for the
    combinations of columns behind them (#1207).
    """
    field_class = OperationStateForm


class BackgroundProcessFilterSet(FilterSet):
    status = ProcessStatusFilter(
        label=_('status'),
        field_name='status',
        help_text=MULTIPLE_VALUES)
    # the state is no column but the annotation of process_info(), so this
    # filter answers on the queryset of the overview, which reads it
    state = OperationStateFilter(
        label=_('state'),
        method='filter_state',
        help_text=MULTIPLE_VALUES)
    # the lookup of the annotation is no model field, so it is not generated
    # from Meta.fields like the `id.in` of an overview. The tabs of the job
    # center ask for a set of states the same way they ask for a set of ids.
    state__in = OperationStateFilter(
        label=_('state'),
        method='filter_state',
        help_text=MULTIPLE_VALUES)

    class Meta:
        model = BackgroundProcess
        fields = {
            'id': ['exact', 'icontains', 'contains', 'in'],
            "process_type": ["exact", "icontains", "contains"],
            "description": ["exact", "icontains", "contains"],
            "phase": ["exact", "icontains", "contains"],
            # one group of the background job center is the set of operations
            # which report about one resource; the drawer asks for it by id
            "related_id": ["exact", "in"],
            # the Background Job Center counts and lists processes by the
            # times they were created and decided (#1207); the history
            # screen of #1208 pages the past by the same moments
            "date_created": ["exact", "gt", "gte", "lt", "lte", "range"],
            "done_at": ["exact", "gt", "gte", "lt", "lte", "range"],
        }

    def filter_state(self, queryset, name, value):
        """Answer the operations which are in one of the asked states.

        The lookup is the annotation `state` itself, whatever the name of the
        filter which asked (`state` or `state__in`).
        """
        return queryset.filter(state__in=value)


class OperationalIncidentFilterSet(FilterSet):
    """The filters of the incident api (#1319).

    The incident api is read-only and answers the questions of the
    notification center: which incidents are standing or resolved (the
    lifecycle), how much attention they ask, which kind of problem they
    are (the code), which service they stand for - including the incidents
    about a job or a run belonging to that service - and the history by its
    moments. Every filter runs over the queryset which the view already
    narrowed to what the caller may see, so a filtered count never names an
    incident hidden from the caller.
    """

    #: the incidents standing for one service: the services answer
    #: themselves, the jobs and runs of a service are answered through their
    #: service relation - the question of every contextual screen of #1322
    service = UUIDFilter(label=_('service'), method='filter_service')

    class Meta:
        model = OperationalIncident
        fields = {
            'id': ['exact', 'in'],
            # the type of an incident is its code
            'code': ['exact', 'in'],
            'source': ['exact', 'in'],
            'severity': ['exact', 'in'],
            # the lifecycle of the incident: the active queue and the
            # resolved history of the notification center ask by it
            'status': ['exact', 'in'],
            'occurrence_count': ['exact', 'gt', 'gte', 'lt', 'lte'],
            'first_occurred_at': ['exact', 'gt', 'gte', 'lt', 'lte', 'range'],
            'last_occurred_at': ['exact', 'gt', 'gte', 'lt', 'lte', 'range'],
            'resolved_at': ['exact', 'gt', 'gte', 'lt', 'lte', 'range'],
            # the drawer of one job or run asks its own incidents by the
            # resource's id; the typed exact filters run over the queryset
            # which the view already narrowed, so a filter can never name an
            # incident the caller may not see
            'web_map_service': ['exact'],
            'web_feature_service': ['exact'],
            'catalogue_service': ['exact'],
            'harvesting_job': ['exact'],
            'web_map_service_update_job': ['exact'],
            'web_feature_service_update_job': ['exact'],
            'catalogue_service_update_job': ['exact'],
            'web_map_service_monitoring_run': ['exact'],
            'web_feature_service_monitoring_run': ['exact'],
            'catalogue_service_monitoring_run': ['exact'],
        }

    def filter_service(self, queryset, name, value):
        """The incidents which stand for one service, jobs and runs alike."""
        return queryset.model.objects.service_scoped(queryset, value)
