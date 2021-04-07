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

REDIS_PORT = '5556'
