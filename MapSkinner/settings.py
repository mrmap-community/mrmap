"""
Django settings for MapSkinner project.

Generated by 'django-admin startproject' using Django 2.1.2.

For more information on this file, see
https://docs.djangoproject.com/en/2.1/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/2.1/ref/settings/
"""

import os

import sys
from django.utils.translation import gettext_lazy as _

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
from service.helper.enums import ConnectionEnum, VersionEnum

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/2.1/howto/deployment/checklist/

VERSION = "0.3.0"
GIT_REPO_URI = "https://git.osgeo.org/gitea/hollsandre/MapSkinner/src/branch/pre_master"

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'k7goig+64=-4ps7a(@-qqa(pdk^8+hq#1a9)^bn^m*j=ix-3j5'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

DATA_UPLOAD_MAX_NUMBER_FIELDS = 10000

HTTP_OR_SSL = "http://"
HOST_NAME = "127.0.0.1:8000"
HOST_IP = "127.0.0.1:8000"
# DEFINE ROOT URL FOR DYNAMIC AJAX REQUEST RESOLVING
ROOT_URL = HTTP_OR_SSL + HOST_NAME

EXEC_TIME_PRINT = "Exec time for %s: %1.5fs"


CATEGORIES = {
    "inspire": "https://www.eionet.europa.eu/gemet/getTopmostConcepts?thesaurus_uri=http://inspire.ec.europa.eu/theme/&language={}",
    "iso": "http://inspire.ec.europa.eu/metadata-codelist/TopicCategory/TopicCategory.{}.json",
}

CATEGORIES_LANG = {
    "locale_1": "de",
    "locale_2": "fr",
}

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
    "inspire_vs": "http://inspire.ec.europa.eu/schemas/inspire_vs/1.0",
    "inspire_dls": "http://inspire.ec.europa.eu/schemas/inspire_dls/1.0",
    "epsg": "urn:x-ogp:spec:schema-xsd:EPSG:1.0:dataset",
    "ms": "http://mapserver.gis.umn.edu/mapserver",
    "xsd": "http://www.w3.org/2001/XMLSchema",
    "sld": "http://www.opengis.net/sld",
    "fes": "http://www.opengis.net/fes/2.0",
}
GENERIC_NAMESPACE_TEMPLATE = "*[local-name()='{}']"

# Session refreshes on every request!
SESSION_EXPIRATION = 30*60  # minutes*seconds
SESSION_SAVE_EVERY_REQUEST = True

# Home/Dashboard settings
LAST_ACTIVITY_DATE_RANGE = 7

# Threshold which indicates when to use multithreading instead of iterative approaches
MULTITHREADING_THRESHOLD = 2000

HTTP_PROXY = "http://10.240.20.164:8080"

PROXIES = {
    "http": HTTP_PROXY,
    "https": HTTP_PROXY,
}

ALLOWED_HOSTS = [
    HOST_NAME,
    "127.0.0.1",
]


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.postgres',
    'django.contrib.gis',
    'service',
    'users',
    'structure',
    'django_extensions',
    'editor',
    'captcha',
    'rest_framework',
    'api',
    'bootstrap4',
    'fontawesome_5',
    'django_tables2',
    'query_parameters',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# Password hashes
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
]

ROOT_URLCONF = 'MapSkinner.urls'

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
            ],
        },
    },
]

WSGI_APPLICATION = 'MapSkinner.wsgi.application'

# Database
# https://docs.djangoproject.com/en/2.1/ref/settings/#databases

DATABASES = {
    'default': {
        #'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': 'mapskinner',
        'USER':'postgres',
        'PASSWORD':'',
        'HOST' : '127.0.0.1',
        'PORT' : ''
    }
}


# Password validation
# https://docs.djangoproject.com/en/2.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


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


TIME_ZONE = 'Europe/Berlin'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# CELERY SETTINGS
BROKER_URL = 'redis://localhost:6379'
CELERY_RESULT_BACKEND = 'redis://localhost:6379'
CELERY_ACCEPT_CONTENT = ['application/json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE


# API
from api.settings import REST_FRAMEWORK

# Tests
if 'test' in sys.argv:
    CAPTCHA_TEST_MODE = True


# Progress bar
PROGRESS_STATUS_AFTER_PARSING = 90  # indicates at how much % status we are after the parsing

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/2.1/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR + "/static/"