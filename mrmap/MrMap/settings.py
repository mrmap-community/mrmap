"""
Django settings for MrMap project.

For more information on this file, see
https://docs.djangoproject.com/en/3.1/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/3.1/ref/settings/
"""

import logging
import os
import socket
import sys

from django.contrib import messages
from django.core.management.utils import get_random_secret_key
from django.utils.translation import gettext_lazy as _
from kombu import Queue, Exchange

# Set the base directory two levels up
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MEDIA_ROOT = os.environ.get("MRMAP_MEDIA_DIR", "/var/mrmap/media")
# create media dir if it does not exist
if not os.path.exists(MEDIA_ROOT):
    os.makedirs(MEDIA_ROOT)

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', get_random_secret_key())

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = int(os.environ.get("DJANGO_DEBUG", default=0))

# Application definition
INSTALLED_APPS = [
    'channels',
    'guardian',
    'dal',
    'dal_select2',
    'django.forms',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.postgres',
    'django.contrib.gis',
    'formtools',
    'django_extensions',
    'captcha',
    'rest_framework',
    'rest_framework.authtoken',
    'django_celery_beat',
    'django_celery_results',
    'bootstrap5',
    'django_tables2',
    'django_filters',
    'query_parameters',
    'django_nose',
    'mathfilters',
    'leaflet',
    'breadcrumb',
    'mptt',
    'MrMap',  # added so we can use general commands in MrMap/management/commands
    'users',
    'acls',
    'jobs',
    'registry',
    'extras',
    'ws',
]

TEMPLATE_LOADERS = (
    'django.template.loaders.extras.custom_template_filters.py'
    'django.template.loaders.app_directories.Loader'
)

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.middleware.gzip.GZipMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.auth.middleware.RemoteUserMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'crum.CurrentRequestUserMiddleware',
]

if DEBUG:
    INSTALLED_APPS.append(
        'debug_toolbar',
    )
    # Disable all panels by default
    DEBUG_TOOLBAR_CONFIG = {
        "DISABLE_PANELS": {
            'debug_toolbar.panels.versions.VersionsPanel',
            'debug_toolbar.panels.timer.TimerPanel',
            'debug_toolbar.panels.settings.SettingsPanel',
            'debug_toolbar.panels.headers.HeadersPanel',
            'debug_toolbar.panels.request.RequestPanel',
            'debug_toolbar.panels.sql.SQLPanel',
            'debug_toolbar.panels.staticfiles.StaticFilesPanel',
            'debug_toolbar.panels.templates.TemplatesPanel',
            'debug_toolbar.panels.cache.CachePanel',
            'debug_toolbar.panels.signals.SignalsPanel',
            'debug_toolbar.panels.logging.LoggingPanel',
            'debug_toolbar.panels.redirects.RedirectsPanel',
            'debug_toolbar.panels.profiling.ProfilingPanel',
        },
        'SHOW_TOOLBAR_CALLBACK': lambda request: True,
    }

    MIDDLEWARE.append('debug_toolbar.middleware.DebugToolbarMiddleware')

if os.environ.get("MRMAP_PRODUCTION") == 'False':
    INSTALLED_APPS.append(
        'behave_django',
    )

# Password hashes
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
]

ROOT_URLCONF = 'MrMap.urls'

FORM_RENDERER = 'django.forms.renderers.TemplatesSetting'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            BASE_DIR + "/templates",
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'MrMap.context_processors.default_context',
                'breadcrumb.context_processors.breadcrumb_renderer',
            ],
        },
    },
]
PER_PAGE_DEFAULT = 25
PER_PAGE_DEFAULTS = [
    25, 50, 100, 250, 500, 1000
]
PER_PAGE_MAX = 2500

METADATA_URL = ["request=GetMetadata&", ]

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost;127.0.0.1;[::1];mrmap-appserver").split(";")

# GIT repo links
GIT_REPO_URI = "https://github.com/mrmap-community/mrmap"
GIT_GRAPH_URI = "https://github.com/mrmap-community/mrmap/graph"

LOGIN_REDIRECT_URL = "users:dashboard"
LOGOUT_REDIRECT_URL = "users:login"
# Defines where to redirect a user, that has to be logged in for a certain route
LOGIN_URL = "users:login"

# Internationalization
# https://docs.djangoproject.com/en/2.1/topics/i18n/
LANGUAGE_CODE = 'en'
LANGUAGES = (
    ('en', _('English')),
    ('de', _('German')),
)
LOCALE_PATHS = (
    os.path.join(BASE_DIR, 'locale'),
)
DEFAULT_DATE_TIME_FORMAT = 'YYYY-MM-DD hh:mm:ss'
TIME_ZONE = os.environ.get('DJANGO_TIME_ZONE')
USE_I18N = True
USE_L10N = True
USE_TZ = True

# Defines the semantic web information which will be injected on the resource html views
SEMANTIC_WEB_HTML_INFORMATION = {
    "legalName": "Zentrale Stelle GDI-RP",
    "email": "kontakt@geoportal.rlp.de",
    "addressCountry": "DE",
    "streetAddress": "Von-Kuhl-Straße 49",
    "addressRegion": "RLP",
    "postalCode": "56070",
    "addressLocality": "Koblenz",
}

# Defines the timespan for fetching the last activities on dashboard
LAST_ACTIVITY_DATE_RANGE = 7

# configure your proxy like "http://10.0.0.1:8080"
# or with username and password: "http://username:password@10.0.0.1:8080"
HTTP_PROXY = ""
PROXIES = {
    "http": HTTP_PROXY,
    "https": HTTP_PROXY,
}

# configure if you want to validate ssl certificates
# it is highly recommend keeping this to true
VERIFY_SSL_CERTIFICATES = True

# django-guardian

AUTHENTICATION_BACKENDS = (
    'django.contrib.auth.backends.ModelBackend',  # default
    'guardian.backends.ObjectPermissionBackend',
)

GUARDIAN_RAISE_403 = True

# django-guardian-roles
GUARDIAN_ROLES_OWNABLE_MODELS = ['registry.Metadata',
                                 'registry.MonitoringRun',
                                 'registry.MonitoringResult',
                                 'registry.HealthState',
                                 'registry.ProxyLog']

GUARDIAN_ROLES_OWNER_FIELD_ATTRIBUTE = 'owned_by_org'
GUARDIAN_ROLES_OLD_OWNER_FIELD_ATTRIBUTE = '_owned_by_org'

GUARDIAN_ROLES_ADMIN_ROLE_FOR_ROLE_ADMIN_ROLE = 'organization_administrator'
GUARDIAN_ROLES_OWNER_MODEL = 'users.Organization'

################################################################
# Database settings
# https://docs.djangoproject.com/en/2.1/ref/settings/#databases
################################################################
DATABASES = {
    "default": {
        "ENGINE": os.environ.get("SQL_ENGINE"),
        "NAME": os.environ.get("SQL_DATABASE"),
        "USER": os.environ.get("SQL_USER"),
        "PASSWORD": os.environ.get("SQL_PASSWORD"),
        "HOST": os.environ.get("SQL_HOST"),
        "PORT": os.environ.get("SQL_PORT"),
    }
}
# To avoid unwanted migrations in the future, either explicitly set DEFAULT_AUTO_FIELD to AutoField:
DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'
################################################################
# Redis settings
################################################################
REDIS_HOST = os.environ.get("REDIS_HOST")
REDIS_PORT = os.environ.get("REDIS_PORT")
BROKER_URL = f'redis://{REDIS_HOST}:{REDIS_PORT}'

# Cache
# Use local redis installation as cache
# The "regular" redis cache will be set to work in redis table 1 (see LOCATION)
# The default table (0) is preserved for celery task management
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": f"{BROKER_URL}/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "COMPRESSOR": "django_redis.compressors.zlib.ZlibCompressor",
        }
    },
}

################################################################
# Celery settings
################################################################
CELERY_RESULT_BACKEND = 'django-db'
CELERY_ACCEPT_CONTENT = ['application/json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
RESPONSE_CACHE_TIME = 60 * 30  # 30 minutes
CELERY_DEFAULT_COUNTDOWN = 5  # custom setting
CELERY_DEFAULT_QUEUE = "default"
CELERY_DEFAULT_EXCHANGE = "default"

CELERY_QUEUES = (
    Queue('default', Exchange('default'), routing_key='default'),
    Queue('download_iso_metadata', Exchange('download_iso_metadata'), routing_key='download_iso_metadata'),
    Queue('download_described_elements', Exchange('download_described_elements'),
          routing_key='download_described_elements'),
    Queue('harvest', Exchange('harvest'), routing_key='harvest'),
)

################################################################
# django channels settings
################################################################
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [(REDIS_HOST, REDIS_PORT)],
            "capacity": 1500,  # default 100
            "expiry": 10,  # default 60
        },
    },
}

# Session settings and password validation
# https://docs.djangoproject.com/en/2.1/ref/settings/#auth-password-validators
MIN_PASSWORD_LENGTH = 9
MIN_USERNAME_LENGTH = 5  # ToDo: For production use another, more appropriate length!
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            "min_length": MIN_PASSWORD_LENGTH,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.1/howto/static-files/
STATIC_URL = '/static/'
STATIC_ROOT = "/var/www/mrmap/static/"
STATICFILES_DIRS = [
    BASE_DIR + '/MrMap/static',
    # TODO research automatic adding of app-specific static dirs
    BASE_DIR + '/registry/static',
]

# static is used for localdev + runserver
if os.path.exists(BASE_DIR + '/static'):
    STATICFILES_DIRS.append(BASE_DIR + '/static')

# /tmp/static is used in docker container
if os.path.exists("/tmp/static"):
    STATICFILES_DIRS.append('/tmp/static')

WSGI_APPLICATION = 'MrMap.wsgi.application'
ASGI_APPLICATION = 'MrMap.asgi.application'

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

# Defines which User model implementation is used for authentication process
AUTH_USER_MODEL = 'users.MrMapUser'

# Defines how many seconds can pass until the session expires, default is 30 * 60
SESSION_COOKIE_AGE = 30 * 60

# Whether the session age will be refreshed on every request or only if data has been modified
SESSION_SAVE_EVERY_REQUEST = True

# define the message tags for bootstrap
MESSAGE_TAGS = {
    messages.DEBUG: 'alert-info',
    messages.INFO: 'alert-info',
    messages.SUCCESS: 'alert-success',
    messages.WARNING: 'alert-warning',
    messages.ERROR: 'alert-danger',
}

################################################################
# nose test runner settings
################################################################
if 'test' in sys.argv:
    CAPTCHA_TEST_MODE = True

TEST_RUNNER = 'django_nose.NoseTestSuiteRunner'
NOSE_ARGS = [
    '--with-xunit',
    f'--xunit-file={BASE_DIR}/xunit-result.xml',
    '--with-coverage',
    '--cover-erase',
    '--cover-xml',
    f'--cover-xml-file={BASE_DIR}/coverage-report.xml',
]

################################################################
# DJANGO DEBUG TOOLBAR
################################################################
# Add the IP for which the toolbar should be shown
INTERNAL_IPS = [
    "127.0.0.1"
]

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
    "csw": "http://www.opengis.net/cat/csw/2.0.2",
}

# Defines a generic template for xml element fetching without caring about the correct namespace
GENERIC_NAMESPACE_TEMPLATE = "*[local-name()='{}']"

################################################################
# Mapserver
################################################################
MAPSERVER_URL = os.environ.get('MAPSERVER_URL')
MAPSERVER_SECURITY_MASK_FILE_PATH = os.environ.get(
    "MAPSERVER_SECURITY_MASK_FILE_PATH")  # path on the machine which provides the mapserver service
MAPSERVER_SECURITY_MASK_TABLE = "registry_allowedoperation"
MAPSERVER_SECURITY_MASK_GEOMETRY_COLUMN = "allowed_area"
MAPSERVER_SECURITY_MASK_KEY_COLUMN = "id"

DEFAULT_SRS = 4326
FONT_IMG_RATIO = 1 / 20  # Font to image ratio
ERROR_MASK_VAL = 1  # Indicates an error while creating the mask ("good" values are either 0 or 255)
ERROR_MASK_TXT = "Error during mask creation! \nCheck the configuration of security_mask.map!"
################################################################
# Logger settings
################################################################
ROOT_LOGGER = logging.getLogger('MrMap.root')

LOG_DIR = os.environ.get("MRMAP_LOG_DIR", f'/var/log/mrmap/{socket.gethostname()}/')
LOG_FILE_MAX_SIZE = 1024 * 1024 * 20  # 20 MB
LOG_FILE_BACKUP_COUNT = 5

# create log dir if it does not exist
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            # see https://docs.python.org/3/library/logging.html#logrecord-attributes for a list of possible attributes
            'format': '{levelname} {asctime} {pathname} {lineno} {module} {process:d} {thread:d}: {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'syslog': {
            'class': 'logging.handlers.SysLogHandler',
            'formatter': 'verbose',
            'facility': 'user',
            'address': ('localhost', 1514),
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'maxBytes': LOG_FILE_MAX_SIZE,
            'backupCount': LOG_FILE_BACKUP_COUNT,
            'filename': LOG_DIR + 'logs.log',
            'formatter': 'verbose',
        }
    },
    'loggers': {
        'MrMap.root': {
            'handlers': ['file', 'syslog'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'disabled': False,
            'propagate': True,
        },
    },
}
