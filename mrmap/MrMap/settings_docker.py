"""
Additional/overwritten settings for Docker dev setup.
"""

from MrMap.settings import *

# for docker-based setups, the host must be reachable by docker containers (e.g. the ETF validator), so
# we cannot use localhost here
HOST_NAME = "172.17.0.1:8000"
ROOT_URL = HTTP_OR_SSL + HOST_NAME

ALLOWED_HOSTS.append("0.0.0.0")
ALLOWED_HOSTS.append("django")
ALLOWED_HOSTS.append("172.17.0.1")


DATABASES['default']['NAME'] = 'mrmap'
DATABASES['default']['USER'] = 'mrmap'
DATABASES['default']['PASSWORD'] = 'mrmap'
DATABASES['default']['PORT'] = '5432'
DATABASES['default']['HOST'] = 'mrmap-postgis'

CACHES['default']['LOCATION'] = 'redis://localhost:5556/1'

BROKER_URL = f'redis://mrmap-redis:6379'
# CELERY_RESULT_BACKEND = 'redis://localhost:5556'

CHANNEL_LAYERS['default']['CONFIG']['hosts'] = [('localhost', '5556')]

MAPSERVER_LOCAL_PATH = "http://127.0.0.1:5557/cgi-bin/mapserv?"
MAPSERVER_SECURITY_MASK_FILE_PATH = "/etc/mapserver/security_mask.map"


pass
