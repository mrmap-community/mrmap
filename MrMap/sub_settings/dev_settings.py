"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 03.09.20

"""
import sys

from django.contrib import messages

from MrMap.sub_settings.django_settings import BASE_DIR

"""
This settings file contains ONLY development relevant settings. 

ONLY CHANGE SETTINGS IN HERE IF YOU ARE A DEVELOPER AND YOU REALLY KNOW WHAT YOU ARE DOING!

"""

# Defines basic server information
HTTP_OR_SSL = "http://"
HOST_NAME = "127.0.0.1:8000"
HOST_IP = "127.0.0.1:8000"

# DEFINE ROOT URL FOR DYNAMIC AJAX REQUEST RESOLVING
ROOT_URL = HTTP_OR_SSL + HOST_NAME

# Extends the number of GET/POST parameters
DATA_UPLOAD_MAX_NUMBER_FIELDS = 10000

# A string template used in the beginnings of this project
EXEC_TIME_PRINT = "Exec time for %s: %1.5fs"

# Defines table page constants
PAGE_SIZE_OPTIONS = [1, 3, 5, 10, 15, 20, 25, 30, 50, 75, 100, 200, 500]
PAGE_SIZE_DEFAULT = 5
PAGE_SIZE_MAX = 100
PAGE_DEFAULT = 1

# Threshold which indicates when to use multithreading instead of iterative approaches
MULTITHREADING_THRESHOLD = 2000

# Holds all apps which needs migrations. Will be used in command 'dev_makemigrations'
# If you added a new app with models, which need to be migrated, you have to put the app's name in this list
MIGRATABLE_APPS = [
    'csw',
    'structure',
    'service',
    'users',
    'monitoring',
]

# Defines which User model implementation is used for authentication process
AUTH_USER_MODEL = 'structure.MrMapUser'

# Defines how many seconds can pass until the session expires, default is 30 * 60
SESSION_COOKIE_AGE = 30 * 60

# Whether the session age will be refreshed on every request or only if data has been modified
SESSION_SAVE_EVERY_REQUEST = True

# Defines where to redirect a user, that has to be logged in for a certain route
LOGIN_URL = "/"

# define the message tags for bootstrap4
MESSAGE_TAGS = {
    messages.DEBUG: 'alert-info',
    messages.INFO: 'alert-info',
    messages.SUCCESS: 'alert-success',
    messages.WARNING: 'alert-warning',
    messages.ERROR: 'alert-danger',
}


# Tests
if 'test' in sys.argv:
    CAPTCHA_TEST_MODE = True

TEST_RUNNER = 'django_nose.NoseTestSuiteRunner'
NOSE_ARGS = [
    '--with-xunit',
    '--xunit-file=tests/nosetests.xml',
    '--with-coverage',
    '--cover-erase',
    '--cover-xml',
    '--cover-xml-file=nosecover.xml',
]

# DJANGO DEBUG TOOLBAR
# Add the IP for which the toolbar should be shown
INTERNAL_IPS = [
    "127.0.0.1"
]

# DEALER Settings
DEALER_PATH = BASE_DIR

# Defines xml namespaces used for xml parsing and creating
XML_NAMESPACES = {
    "ogc": "http://www.opengis.net/ogc",
    "ows": "http://www.opengis.net/ows",
    "wfs": "http://www.opengis.net/wfs",
    "wms": "http://www.opengis.net/wms",
    "xlink": "http://www.w3.org/1999/xlink",
    "gml": "http://www.opengis.net/gml",
    "gmd": "http://www.isotc211.org/2005/gmd",
    "gco": "http://www.isotc211.org/2005/gco",
    "srv": "http://www.isotc211.org/2005/srv",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
    "ave": "http://repository.gdi-de.org/schemas/adv/produkt/alkis-vereinfacht/1.0",
    "inspire_common": "http://inspire.ec.europa.eu/schemas/common/1.0",
    "inspire_com": "http://inspire.ec.europa.eu/schemas/common/1.0",
    "inspire_vs": "http://inspire.ec.europa.eu/schemas/inspire_vs/1.0",
    "inspire_ds": "http://inspire.ec.europa.eu/schemas/inspire_ds/1.0",
    "inspire_dls": "http://inspire.ec.europa.eu/schemas/inspire_dls/1.0",
    "epsg": "urn:x-ogp:spec:schema-xsd:EPSG:1.0:dataset",
    "ms": "http://mapserver.gis.umn.edu/mapserver",
    "se": "http://www.opengis.net/se",
    "xsd": "http://www.w3.org/2001/XMLSchema",
    "sld": "http://www.opengis.net/sld",
    "fes": "http://www.opengis.net/fes/2.0",
}

# Defines a generic template for xml element fetching without caring about the correct namespace
GENERIC_NAMESPACE_TEMPLATE = "*[local-name()='{}']"