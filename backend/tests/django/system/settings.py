"""Isolated, database-free tests for the status API."""
SECRET_KEY = 'status-tests-only'
USE_TZ = True
TIME_ZONE = 'UTC'
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
INSTALLED_APPS = ['django.contrib.auth', 'django.contrib.contenttypes', 'guardian', 'django_celery_beat', 'system']
ROOT_URLCONF = 'system.urls'
JSON_API_FORMAT_FIELD_NAMES = 'camelize'
REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': ['rest_framework_json_api.renderers.JSONRenderer'],
}
CACHES = {'default': {'BACKEND': 'django_redis.cache.RedisCache', 'LOCATION': 'redis://localhost:6379/1'}}
AUTHENTICATION_BACKENDS = ['django.contrib.auth.backends.ModelBackend', 'guardian.backends.ObjectPermissionBackend']
