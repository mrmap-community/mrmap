import uuid

from django.contrib.gis.geos import Polygon, GEOSGeometry
from django.contrib.postgres.forms import SplitArrayField
from django.forms import DecimalField
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


class MrMapApiSearchFilter(FilterSet):
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

    bbox = BoundingBoxFilter(
        method='bbox_filter',
        label='Bounding Box',
        base_field=DecimalField(required=False, decimal_places=3, max_digits=6, max_value=180.000, min_value=-180.000),
        size=4,
        remove_trailing_nulls=True
    )

    @staticmethod
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
        bbox_polygon = GEOSGeometry(Polygon.from_bbox(bbox_coords), srid=4326)  # [xmin, ymin, xmax, ymax]
        return queryset.filter(bbox_lat_lon__intersects=bbox_polygon)
