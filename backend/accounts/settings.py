# days
DEFAULT_REQUEST_ACIVATION_TIME = 30

# In hours: how long an activation link is valid for a user
USER_ACTIVATION_TIME_WINDOW = 24

SECURED_MODELS = ['registry.WebMapService',
                  'registry.WebFeatureService']


DEFAULT_SETTINGS_FOR_REACT_CLIENT = {
    'tables': {
        'WebMapService': {
            'columns': ['title', 'version', 'createdAt', 'actions']
        },
        'WebFeatureService': {
            'columns': ['title', 'version', 'createdAt', 'actions']
        },
        'CatalougeService': {
            'columns': ['title', 'version', 'createdAt', 'actions']
        }
    }
}
