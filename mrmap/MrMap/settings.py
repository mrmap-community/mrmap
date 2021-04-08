"""
Django settings for MrMap project.

For more information on this file, see
https://docs.djangoproject.com/en/3.1/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/3.1/ref/settings/
"""

# Include other settings files (DO NOT TOUCH THESE!)
from MrMap.sub_settings.django_settings import *
from MrMap.sub_settings.dev_settings import *
from MrMap.sub_settings.logging_settings import *
from api.settings import REST_FRAMEWORK

ALLOWED_HOSTS = [
    HOST_NAME,
    "127.0.0.1",
    "localhost",
]

# GIT repo links
GIT_REPO_URI = "https://github.com/mrmap-community/mrmap"
GIT_GRAPH_URI = "https://github.com/mrmap-community/mrmap/graph"

LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"
LOGIN_URL = "login"

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

################################################################
# Database settings
# https://docs.djangoproject.com/en/2.1/ref/settings/#databases
################################################################

DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': 'MrMap',
        'USER': 'postgres',
        'HOST': '127.0.0.1',
        'PORT': '5432',
    }
}

################################################################
# Redis settings
################################################################
REDIS_HOST = 'localhost'
REDIS_PORT = '6379'
BROKER_URL = f'redis://{REDIS_HOST}:{REDIS_PORT}'

# Cache
# Use local redis installation as cache
# The "regular" redis cache will be set to work in redis table 1 (see LOCATION)
# The default table (0) is preserved for celery task management
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": f"redis://{REDIS_HOST}:{REDIS_PORT}/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "COMPRESSOR": "django_redis.compressors.zlib.ZlibCompressor",
        }
    }
}

################################################################
# Celery settings
################################################################
CELERY_RESULT_BACKEND = f'redis://{REDIS_HOST}:{REDIS_PORT}'
CELERY_ACCEPT_CONTENT = ['application/json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
RESPONSE_CACHE_TIME = 60 * 30  # 30 minutes

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
