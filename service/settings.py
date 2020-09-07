"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 23.09.19

"""

import os

from django.contrib.gis.geos import Polygon, GEOSGeometry
from django.utils.translation import gettext_lazy as _

from MrMap.settings import BASE_DIR, HTTP_OR_SSL, HOST_NAME, STATIC_ROOT
from service.helper.enums import ConnectionEnum, OGCServiceVersionEnum
import logging

service_logger = logging.getLogger('MrMap.service')

# Some special things
DEFAULT_CONNECTION_TYPE = ConnectionEnum.REQUESTS
DEFAULT_SERVICE_VERSION = OGCServiceVersionEnum.V_1_1_1

# Default metadata language
## Has to match the language code, defined by ISO19115
DEFAULT_MD_LANGUAGE = "ger"
ISO_19115_LANG_CHOICES = [
    ("ger", _("German")),
    ("eng", _("English")),
]

# semantic relation types
MD_RELATION_TYPE_VISUALIZES = "visualizes"
MD_RELATION_TYPE_DESCRIBED_BY = "describedBy"

SERVICE_OPERATION_URI_TEMPLATE = "{}{}/resource/metadata/".format(HTTP_OR_SSL, HOST_NAME) + "{}" + "/operation?"
SERVICE_DATASET_URI_TEMPLATE = "{}{}/resource/metadata/".format(HTTP_OR_SSL, HOST_NAME) + "dataset/{}"
SERVICE_METADATA_URI_TEMPLATE = "{}{}/resource/metadata/".format(HTTP_OR_SSL, HOST_NAME) + "{}"
HTML_METADATA_URI_TEMPLATE = "{}{}/resource/metadata/html/".format(HTTP_OR_SSL, HOST_NAME) + "{}"
SERVICE_LEGEND_URI_TEMPLATE = "{}{}/resource/metadata/".format(HTTP_OR_SSL, HOST_NAME) + "{}" + "/legend/" + "{}"

REQUEST_TIMEOUT = 100  # seconds

# security proxy settings
MAPSERVER_LOCAL_PATH = "http://127.0.0.1/cgi-bin/mapserv"
MAPSERVER_SECURITY_MASK_FILE_PATH = os.path.join(os.path.dirname(__file__), "mapserver/security_mask.map")
MAPSERVER_SECURITY_MASK_TABLE = "service_securedoperation"
MAPSERVER_SECURITY_MASK_GEOMETRY_COLUMN = "bounding_geometry"
MAPSERVER_SECURITY_MASK_KEY_COLUMN = "id"

EXTERNAL_AUTHENTICATION_FILEPATH = "{}/../ext_auth_keys".format(BASE_DIR)

# Defines the possible FeatureTypeElement type names, which hold the geometry of a feature type
ALLLOWED_FEATURE_TYPE_ELEMENT_GEOMETRY_IDENTIFIERS = [
    'GeometryPropertyType',
    'PointPropertyType',
    'LineStringPropertyType',
    'PolygonPropertyType',
    'MultiPointPropertyType',
    'MultiLineStringPropertyType',
    'MultiPolygonPropertyType'
]

DEFAULT_SRS_FAMILY = "EPSG"
DEFAULT_SRS = 4326
DEFAULT_SRS_STRING = "{}:{}".format(DEFAULT_SRS_FAMILY, DEFAULT_SRS)

# Default service bounding box
DEFAULT_SERVICE_BOUNDING_BOX = GEOSGeometry(Polygon.from_bbox([5.866699, 48.908059, 8.76709, 50.882243]), srid=DEFAULT_SRS)
DEFAULT_SERVICE_BOUNDING_BOX_EMPTY = GEOSGeometry(Polygon.from_bbox([0.0, 0.0, 0.0, 0.0]), srid=DEFAULT_SRS)

ALLOWED_SRS = [
    4326,
    4258,
    31466,
    31467,
    31468,
    25832,
    3857,
]

ALLOWED_SRS_EXTENTS = {

    4326: {
        "minx": -180,
        "miny": -90,
        "maxx": 180,
        "maxy": 90,
        },
    4258: {
        "minx": -10.6700,
        "miny": 34.5000,
        "maxx": 31.5500,
        "maxy": 71.0500,
        },
    31466: {
        "minx": 5.1855468,
        "miny": 46.8457031,
        "maxx": 15.46875,
        "maxy": 55.634765,
        },
    31467: {
        "minx": 5.1855468,
        "miny": 46.8457031,
        "maxx": 15.46875,
        "maxy": 55.634765,
        },
    31468: {
        "minx": 5.1855468,
        "miny": 46.8457031,
        "maxx": 15.46875,
        "maxy": 55.634765,
        },
    25832: {
        "minx": 5.1855468,
        "miny": 46.8457031,
        "maxx": 15.46875,
        "maxy": 55.634765,
        },
    3857: {
        "minx": -180,
        "miny": -90,
        "maxx": 180,
        "maxy": 90,
        },
}

INSPIRE_LEGISLATION_FILE = BASE_DIR + "/inspire_legislation.json"

# MASK CREATION
ERROR_MASK_VAL = 1  # Indicates an error while creating the mask ("good" values are either 0 or 255)
ERROR_MASK_TXT = "Error during mask creation! \nCheck the configuration of security_mask.map!"

# IMAGE RENDERING
MIN_FONT_SIZE = 14  # The minimum font size for text on images
MAX_FONT_SIZE = 20  # The maximum font size for text on images
FONT_IMG_RATIO = 1/20  # Font to image ratio
RENDER_TEXT_ON_IMG = False  # Whether to render 'Access denied for xy' on GetMap responses or not
PREVIEW_MIME_TYPE_DEFAULT = "png"   # Specify a preferred default mime type (without "image/..." prefix) for rendering preview images (e.g. HTML metadata view)

# PREVIEW IMAGE REQUESTING
PLACEHOLDER_IMG_PATH = STATIC_ROOT + "images/mr_map_404.png"

# PROXY LOG
COUNT_DATA_PIXELS_ONLY = True  # If True, the response megapixel will be computed without transparent (alpha) pixel.
LOGABLE_FEATURE_RESPONSE_FORMATS = [
    "csv",
    "geojson",
    "kml",
    "gml2",
    "gml3",
]

# DIMENSION
DIMENSION_TYPE_CHOICES = [
    ("time", "time"),
    ("elevation", "elevation"),
    ("other", "other"),
]

NONE_UUID = "00000000-0000-0000-0000-000000000000"

# Progress bar
PROGRESS_STATUS_AFTER_PARSING = 90  # indicates at how much % status we are after the parsing