"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 03.09.20

"""
import os
from django.utils.translation import gettext_lazy as _

"""
This settings file contains all django framework related settings. Similar to dev_settings.py:

ONLY CHANGE SETTINGS IN HERE IF YOU ARE A DEVELOPER AND YOU REALLY KNOW WHAT YOU ARE DOING!

"""

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.dirname(
            os.path.abspath(
                __file__
            )
        )
    )
)

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'k7goig+64=-4ps7a(@-qqa(pdk^8+hq#1a9)^bn^m*j=ix-3j5'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# Application definition
INSTALLED_APPS = [
    'MrMap',  # added so we can use general commands in MrMap/management/commands
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
    'service',
    'users',
    'structure',
    'django_extensions',
    'editor',
    'captcha',
    'rest_framework',
    'rest_framework.authtoken',
    'api',
    'csw',
    'django_celery_beat',
    'monitoring',
    'bootstrap4',
    'fontawesome_5',
    'django_tables2',
    'django_filters',
    'query_parameters',
    'django_nose',
    'mathfilters',
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
        }
    }


TEMPLATE_LOADERS = (
    'django.template.loaders.structure.mr_map_filters.py',
)

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.middleware.gzip.GZipMiddleware',
    'debug_toolbar.middleware.DebugToolbarMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.auth.middleware.RemoteUserMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'dealer.contrib.django.Middleware',
]

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
                'dealer.contrib.django.context_processor',
            ],
        },
    },
]

WSGI_APPLICATION = 'MrMap.wsgi.application'


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
TIME_ZONE = 'Europe/Berlin'
USE_I18N = True
USE_L10N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.1/howto/static-files/
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR + "/static/"
STATICFILES_DIRS = [
    BASE_DIR + '/MrMap/static',
]
