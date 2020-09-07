import django_filters
from django import forms
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q

from MrMap.filtersets import MrMapFilterSet
from MrMap.widgets import BootstrapDatePickerRangeWidget
from service.helper.enums import OGCServiceEnum, MetadataRelationEnum
from service.models import Metadata, Layer, FeatureType, ProxyLog, ServiceType
from django.utils.translation import gettext_lazy as _

from structure.models import MrMapGroup, MrMapUser


class ChildLayerFilter(django_filters.FilterSet):
    child_layer_title = django_filters.CharFilter(field_name='metadata',
                                                  lookup_expr='title__icontains',
                                                  label=_('Layer title contains'))

    class Meta:
        model = Layer
        fields = []


class FeatureTypeFilter(django_filters.FilterSet):
    child_layer_title = django_filters.CharFilter(field_name='metadata',
                                                  lookup_expr='title__icontains',
                                                  label=_('Featuretype tile contains'))

    class Meta:
        model = FeatureType
        fields = []


class MetadataWmsFilter(django_filters.FilterSet):
    wms_search = django_filters.CharFilter(method='filter_search_over_all',
                                           label=_('Search'))
    show_layers = django_filters.BooleanFilter(
        widget=forms.CheckboxInput(),
        label=_("Show layers"),
        method='filter_layers',
        required=False,
        initial=False,
    )

    @staticmethod
    def filter_search_over_all(queryset, name, value):  # parameter name is needed cause 3 values are expected

        return queryset.filter(title__icontains=value) | \
               queryset.filter(contact__organization_name__icontains=value) | \
               queryset.filter(service__created_by__name__icontains=value) | \
               queryset.filter(service__published_for__organization_name__icontains=value) | \
               queryset.filter(created__icontains=value)

    @staticmethod
    def filter_layers(queryset, name, value):
        queryset = queryset.filter(
            service__is_root=not value
        )
        return queryset

    class Meta:
        model = Metadata
        fields = []


class MetadataWfsFilter(django_filters.FilterSet):
    wfs_search = django_filters.CharFilter(method='filter_search_over_all',
                                           label=_('Search'))

    @staticmethod
    def filter_search_over_all(queryset, name, value):  # parameter name is needed cause 3 values are expected

        return queryset.filter(title__icontains=value) | \
               queryset.filter(contact__organization_name__icontains=value) | \
               queryset.filter(service__created_by__name__icontains=value) | \
               queryset.filter(service__published_for__organization_name__icontains=value) | \
               queryset.filter(created__icontains=value)

    class Meta:
        model = Metadata
        fields = []


class MetadataCswFilter(django_filters.FilterSet):
    wfs_search = django_filters.CharFilter(method='filter_search_over_all',
                                           label=_('Search'))

    @staticmethod
    def filter_search_over_all(queryset, name, value):  # parameter name is needed cause 3 values are expected

        return queryset.filter(title__icontains=value) | \
               queryset.filter(service__created_by__name__icontains=value)

    class Meta:
        model = Metadata
        fields = []


class ProxyLogTableFilter(MrMapFilterSet):
    dr = django_filters.DateTimeFromToRangeFilter(
        label=_("Timestamp"),
        field_name='timestamp',
        method='filter_date_range',
        widget=BootstrapDatePickerRangeWidget(),
        help_text=_("Search in a date range.")
    )
    t = django_filters.ChoiceFilter(
        label=_("Service type"),
        field_name='metadata__service__service_type__name',
        choices=[
            (OGCServiceEnum.WMS.value, OGCServiceEnum.WMS.value),
            (OGCServiceEnum.WFS.value, OGCServiceEnum.WFS.value)
        ],
        help_text=_("Filter by a service type.")
    )
    s = django_filters.CharFilter(
        label=_("Service title"),
        field_name='metadata__title',
        lookup_expr='icontains',
        help_text=_("Filter by the title of a service.")
    )
    mid = django_filters.UUIDFilter(
        label=_("Metadata ID"),
        field_name='metadata__id',
        help_text=_("Filter by the ID of the metadata (#123 in service title).")
    )
    u = django_filters.CharFilter(
        label=_("User"),
        field_name='user',
        lookup_expr='username__icontains',
        help_text=_("Filter by a username.")
    )
    g = django_filters.NumberFilter(
        min_value=1,
        label=_("User group"),
        method="filter_logged_group",
        help_text=_("Filter by the ID of a group.")
    )

    def filter_logged_group(self, queryset, name, value):
        """ Filters by a group id, which the logged user must be a member of.

        Due to our group->MrMapGroup architecture and the public group system, we need an extra filter method.

        Args:
            queryset: The queryset to be filtered
            name: The parameter name
            value: THe parameter value
        Returns:
            queryset: The filtered queryset
        """
        if value is not None:
            try:
                user_group = MrMapGroup.objects.get(id=value)
                users = MrMapUser.objects.filter(
                    groups=user_group
                )

                q =Q()
                q |= Q(user__in=users)

                # If a public group is requested, we need to make sure that GuestUser/AnonymousUser logs are returned as well
                if user_group.is_public_group:
                    q |= Q(user=None)

                queryset = queryset.filter(
                    q
                )
            except ObjectDoesNotExist:
                pass
        return queryset

    def filter_date_range(self, queryset, name, value):
        """ Replaces start and stop range DateTime with 00:00:00 and 23:59:59 to cover full days

        Args:
            queryset: The queryset to be filtered
            name: The parameter name
            value: THe parameter value
        Returns:
            queryset: The filtered queryset
        """
        start = value.start.replace(hour=0, minute=0, second=0)
        stop = value.stop.replace(hour=23, minute=59, second=59)
        queryset = queryset.filter(
            timestamp__gte=start,
            timestamp__lte=stop
        )
        return queryset

    class Meta:
        model = ProxyLog
        fields = []


class MetadataDatasetFilter(django_filters.FilterSet):
    ds = django_filters.CharFilter(
        method='filter_search_over_all',
        label=_('Search')
    )
    dsh = django_filters.BooleanFilter(
        method='filter_show_harvested',
        widget=forms.CheckboxInput(),
        label=_('Show harvested'),
    )

    @staticmethod
    def filter_show_harvested(queryset, name, value):
        """ Filters dataset records for table

        Includes/Excludes harvested results identified by their related_metadata relation_type values

        Args:
            queryset: The queryset to be filtered
            name: The parameter name
            value: The parameter value
        Returns:
             queryset: The filtered queryset
        """
        if value:
            # include harvested ones - do not filter anything
            pass
        else:
            queryset = queryset.exclude(
                related_metadata__relation_type=MetadataRelationEnum.HARVESTED_THROUGH.value
            )
        return queryset

    @staticmethod
    def filter_search_over_all(queryset, name, value):  # parameter name is needed cause 3 values are expected

        return queryset.filter(title__icontains=value)

    class Meta:
        model = Metadata
        fields = []
