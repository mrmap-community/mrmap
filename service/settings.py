"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 23.09.19

"""

import os

from django.contrib.gis.geos import Polygon, GEOSGeometry

from MapSkinner.settings import BASE_DIR
from service.helper.enums import ConnectionEnum, VersionEnum

# Metadata types
MD_TYPE_FEATURETYPE = "featuretype"
MD_TYPE_DATASET = "dataset"
MD_TYPE_SERVICE = "service"
MD_TYPE_LAYER = "layer"

# Some special things
DEFAULT_CONNECTION_TYPE = ConnectionEnum.REQUESTS
DEFAULT_SERVICE_VERSION = VersionEnum.V_1_1_1

# semantic relation types
MD_RELATION_TYPE_VISUALIZES = "visualizes"
MD_RELATION_TYPE_DESCRIBED_BY = "describedBy"

REQUEST_TIMEOUT = 10  # seconds

# security proxy settings
MAPSERVER_LOCAL_PATH = "http://127.0.0.1/cgi-bin/mapserv"
MAPSERVER_SECURITY_MASK_FILE_PATH = os.path.join(os.path.dirname(__file__), "mapserver/security_mask.map")
MAPSERVER_SECURITY_MASK_TABLE = "service_securedoperation"
MAPSERVER_SECURITY_MASK_GEOMETRY_COLUMN= "bounding_geometry"
MAPSERVER_SECURITY_MASK_KEY_COLUMN= "id"


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

# IMAGE RENDERING
MIN_FONT_SIZE = 16  # The minimum font size for
FONT_IMG_RATIO = 40  # Font has 1/FONT_IMG_RATIO ratio