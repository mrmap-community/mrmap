import uuid

from django.contrib.postgres.forms import SplitArrayField
from django.forms import IntegerField
from django_filters import rest_framework as api_filters, FilterSet, Filter
from django_filters.widgets import RangeWidget


LANGUAGE_CHOICES = (
    (0, 'en'),
    (1, 'de')
)


def validate_uuid(uuid_string):
    try:
        uuid.UUID(uuid_string)
    except ValueError:
        return False
    return True


class BoundingBoxFilter(Filter):
    field_class = SplitArrayField

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class MrMapSearchFilter(FilterSet):
    """
    This filter can be used to filter Services by different values in API views or viewsets.
    See https://django-filter.readthedocs.io/en/stable/guide/rest_framework.html
    """

    class Meta:
        abstract = True

    search = api_filters.CharFilter(method='search_filter', label='Search')

    registration = api_filters.DateFromToRangeFilter(
        widget=RangeWidget(
            attrs={'type': 'date'}
        ),
        method='registration_date_range_filter',
        label='Registration Date'
    )
    datestamp = api_filters.DateFromToRangeFilter(
        widget=RangeWidget(
            attrs={'type': 'date'}
        ),
        method='datestamp_range_filter',
        label='Date Stamp'
    )
    # bbox = BoundingBoxFilter(
    #   method='bbox_filter',
    #   label='Bounding Box',
    #   base_field=IntegerField(required=False),
    #   delimiter=';'
    # )
    bbox = BoundingBoxFilter(
        method='bbox_filter',
        label='Bounding Box',
        base_field=IntegerField(required=False),
        size=4,
        remove_trailing_nulls=False
    )

    @ staticmethod
    def search_filter(queryset, name, value):
        return queryset

    def language_filter(self):
        # TODO: language comes from AbstractMetadata model. Currently language is not available
        pass

    @staticmethod
    def registration_date_range_filter(queryset, name, _range):
        start_date = _range.start
        end_date = _range.stop
        return queryset.filter(created_at__gte=start_date, created_at__lte=end_date)

    @staticmethod
    def datestamp_range_filter(queryset, name, _range):
        start_date = _range.start
        end_date = _range.stop
        return queryset.filter(date_stamp__gte=start_date, date_stamp__lte=end_date)

    @staticmethod
    def bbox_filter(queryset, name, bbox_coords):
        # bbox_polygon = Polygon.from_bbox(bbox_coords)  # [xmin, ymin, xmax, ymax]
        # unique_services = list()
        # layer_within_bbox = Layer.objects.filter(bbox_lat_lon__intersects=bbox_polygon)
        # layers = LayerSerializer(layer_within_bbox, many=True).data
        # for layer in layers:
        #     if layer['service'] not in unique_services:
        #         unique_services.append(layer['service'])
        # feature_type_within_bbox = FeatureType.objects.filter(bbox_lat_lon__intersects=bbox_polygon)
        # feature_types = FeatureTypeSerializer(feature_type_within_bbox, many=True).data
        # for feature_type in feature_types:
        #     if feature_type['service'] not in unique_services:
        #         unique_services.append(feature_type['service'])
        # return queryset.filter(id__in=unique_services)
        return queryset
