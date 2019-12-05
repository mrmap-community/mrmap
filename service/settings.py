"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 23.09.19

"""

import os

from django.contrib.gis.geos import Polygon, GEOSGeometry

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


# Default service bounding box
DEFAULT_SERVICE_BOUNDING_BOX = GEOSGeometry(Polygon.from_bbox([5.866699, 48.908059, 8.76709, 50.882243]), srid="EPSG:4326")