"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 03.09.20

"""
import logging

from MrMap.sub_settings.django_settings import BASE_DIR

"""
This settings file contains ONLY development relevant settings. 

ONLY CHANGE SETTINGS IN HERE IF YOU ARE A DEVELOPER AND YOU REALLY KNOW WHAT YOU ARE DOING!

"""
root_logger = logging.getLogger('MrMap.root')

LOG_DIR = BASE_DIR + '/logs'
LOG_SUB_DIRS = {
    'root': {'dir': '/root', 'log_file': 'root.log'},
    'api': {'dir': '/api', 'log_file': 'api.log'},
    'csw': {'dir': '/csw', 'log_file': 'csw.log'},
    'editor': {'dir': '/editor', 'log_file': 'rooeditorog'},
    'monitoring': {'dir': '/monitoring', 'log_file': 'monitoring.log'},
    'service': {'dir': '/service', 'log_file': 'service.log'},
    'structure': {'dir': '/structure', 'log_file': 'structure.log'},
    'users': {'dir': '/users', 'log_file': 'users.log'},
}
LOG_FILE_MAX_SIZE = 1024 * 1024 * 20  # 20 MB
LOG_FILE_BACKUP_COUNT = 5

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d}: {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'MrMap.root.file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'maxBytes': LOG_FILE_MAX_SIZE,
            'backupCount': LOG_FILE_BACKUP_COUNT,
            'filename': LOG_DIR + LOG_SUB_DIRS['root']['dir'] + '/' + LOG_SUB_DIRS['root']['log_file'],
            'formatter': 'verbose',
        },
        'MrMap.api.file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'maxBytes': LOG_FILE_MAX_SIZE,
            'backupCount': LOG_FILE_BACKUP_COUNT,
            'filename': LOG_DIR + LOG_SUB_DIRS['api']['dir'] + '/' + LOG_SUB_DIRS['api']['log_file'],
            'formatter': 'verbose',
        },
        'MrMap.csw.file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'maxBytes': LOG_FILE_MAX_SIZE,
            'backupCount': LOG_FILE_BACKUP_COUNT,
            'filename': LOG_DIR + LOG_SUB_DIRS['csw']['dir'] + '/' + LOG_SUB_DIRS['csw']['log_file'],
            'formatter': 'verbose',
        },
        'MrMap.editor.file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'maxBytes': LOG_FILE_MAX_SIZE,
            'backupCount': LOG_FILE_BACKUP_COUNT,
            'filename': LOG_DIR + LOG_SUB_DIRS['editor']['dir'] + '/' + LOG_SUB_DIRS['editor']['log_file'],
            'formatter': 'verbose',
        },
        'MrMap.monitoring.file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'maxBytes': LOG_FILE_MAX_SIZE,
            'backupCount': LOG_FILE_BACKUP_COUNT,
            'filename': LOG_DIR + LOG_SUB_DIRS['monitoring']['dir'] + '/' + LOG_SUB_DIRS['monitoring']['log_file'],
            'formatter': 'verbose',
        },
        'MrMap.service.file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'maxBytes': LOG_FILE_MAX_SIZE,
            'backupCount': LOG_FILE_BACKUP_COUNT,
            'filename': LOG_DIR + LOG_SUB_DIRS['service']['dir'] + '/' + LOG_SUB_DIRS['service']['log_file'],
            'formatter': 'verbose',
        },
        'MrMap.structure.file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'maxBytes': LOG_FILE_MAX_SIZE,
            'backupCount': LOG_FILE_BACKUP_COUNT,
            'filename': LOG_DIR + LOG_SUB_DIRS['structure']['dir'] + '/' + LOG_SUB_DIRS['structure']['log_file'],
            'formatter': 'verbose',
        },
        'MrMap.users.file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'maxBytes': LOG_FILE_MAX_SIZE,
            'backupCount': LOG_FILE_BACKUP_COUNT,
            'filename': LOG_DIR + LOG_SUB_DIRS['users']['dir'] + '/' + LOG_SUB_DIRS['users']['log_file'],
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'MrMap.root': {
            'handlers': ['MrMap.root.file', ],
            'level': 'INFO',
            'propagate': True,
        },
        'MrMap.api': {
            'handlers': ['MrMap.api.file', ],
            'level': 'INFO',
            'propagate': True,
        },
        'MrMap.csw': {
            'handlers': ['MrMap.csw.file', ],
            'level': 'INFO',
            'propagate': True,
        },
        'MrMap.editor': {
            'handlers': ['MrMap.editor.file', ],
            'level': 'INFO',
            'propagate': True,
        },
        'MrMap.monitoring': {
            'handlers': ['MrMap.monitoring.file', ],
            'level': 'INFO',
            'propagate': True,
        },
        'MrMap.service': {
            'handlers': ['MrMap.service.file', ],
            'level': 'INFO',
            'propagate': True,
        },
        'MrMap.structure': {
            'handlers': ['MrMap.structure.file', ],
            'level': 'INFO',
            'propagate': True,
        },
        'MrMap.users': {
            'handlers': ['MrMap.users.file', ],
            'level': 'INFO',
            'propagate': True,
        },
    },
}
