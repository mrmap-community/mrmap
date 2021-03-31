#!/usr/bin/env python
import os
import sys
# Get an instance of a logger
from MrMap.settings import LOG_DIR, LOG_SUB_DIRS, root_logger

# create log dir if it does not exist
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# create sub log dir if it does not exist
for key, value in LOG_SUB_DIRS.items():
    if not os.path.exists(LOG_DIR + value['dir']):
        os.makedirs(LOG_DIR + value['dir'])

if __name__ == '__main__':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MrMap.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)
    root_logger.warning('MrMap was stopped.')

