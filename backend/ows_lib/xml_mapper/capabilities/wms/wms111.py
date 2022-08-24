
import datetime
from collections.abc import Iterable
from typing import Callable, List
from urllib import parse

from django.conf import settings
from django.contrib.gis.geos import Polygon
from django.utils import timezone
from eulxml.xmlmap import (FloatField, IntegerField, NodeField, NodeListField,
                           SimpleBooleanField, StringField, StringListField,
                           XmlObject)
from isodate.duration import Duration
from isodate.isodates import parse_date
from isodate.isodatetime import datetime_isoformat, parse_datetime
from isodate.isoduration import duration_isoformat, parse_duration
from isodate.isoerror import ISO8601Error
from ows_lib.xml_mapper.mixins import DBModelConverterMixin
from ows_lib.xml_mapper.namespaces import WMS_1_3_0_NAMESPACE, XLINK_NAMESPACE
from registry.xmlmapper.exceptions import SemanticError


class WebMapServiceDefaultSettings(DBModelConverterMixin, XmlObject):
    ROOT_NAMESPACES = {
        "xlink": XLINK_NAMESPACE
    }
