# Based on the objects which can be owned by a organization, two default acl's will be created with default permissions
# 1. => Administrator acl; grants view, change, delete and add permissions
# 2. => Member acl; grants view permission
OWNABLE_MODELS = ['service.Metadata',
                  'monitoring.MonitoringRun',
                  'monitoring.MonitoringResult',
                  'monitoring.HealthState',
                  'service.ProxyLog',
                  'acl.AccessControlList']

DEFAULT_ADMIN_PERMISSIONS = ['view',
                             'change',
                             'delete',
                             'add']

DEFAULT_ORGANIZATION_ADMIN_PERMISSIONS = ['view', 'change']

DEFAULT_MEMBER_PERMISSIONS = ['view']
