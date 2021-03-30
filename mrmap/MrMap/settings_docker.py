"""
Additional/overwritten settings for Docker dev setup.
"""

from MrMap.settings import *

ALLOWED_HOSTS.append("0.0.0.0")
ALLOWED_HOSTS.append("django")


DATABASES['default']['NAME'] = 'mrmap'
DATABASES['default']['USER'] = 'mrmap'
DATABASES['default']['PASSWORD'] = 'mrmap'
DATABASES['default']['PORT'] = '5555'

CACHES['default']['LOCATION'] = 'redis://localhost:5556/1'

BROKER_URL = 'redis://localhost:5556'
CELERY_RESULT_BACKEND = 'redis://localhost:5556'
