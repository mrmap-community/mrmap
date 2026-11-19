# days
DEFAULT_REQUEST_ACIVATION_TIME = 30

# In hours: how long an activation link is valid for a user
USER_ACTIVATION_TIME_WINDOW = 24

#: The models whose instances take part in ownership and role grants (#735).
#:
#: A role-managed model is a *resource*: an instance of it knows the
#: organization which owns it, and the permission bootstrap of
#: ``accounts.signals`` grants a new instance to those roles of the owning
#: organization whose definition may change it
#: (``accounts.managers.roles.RoleQuerySet.managing``). The list is what the
#: bootstrap connects itself to, so a model which is added to it needs no
#: role-group naming scheme and no migration for the organizations which
#: already exist (#727) - but it does need the model itself to be equipped: a
#: typed owner field which answers the owning organization, and the dedicated
#: guardian tables of ``GUARDIAN_PERF_MODELS`` below.
#: ``accounts.checks`` is the guard which refuses the list while an entry is
#: not equipped, so a model cannot be declared ahead of its schema and
#: silently answer its permissions from the generic tables.
#:
#: ``registry.CatalogueService`` is deliberately not listed, although #733
#: gave it an owner and it has its tables: no definition of the role catalogue
#: holds ``change_catalogueservice``, so no role would be granted a new record
#: and the bootstrap would only log for every harvested record. It joins this
#: list together with the definition which manages it, and the check then
#: asks for the equipment it already has.
ROLE_MANAGED_MODELS = ['registry.WebMapService',
                       'registry.WebFeatureService']

#: The models which answer their object permissions from a pair of dedicated
#: ``…UserObjectPermission`` / ``…GroupObjectPermission`` tables (#735).
#:
#: Guardian keeps the object grants of *every* model in one generic pair
#: otherwise, naming the object by content type and the **text** of its
#: primary key; the cast of that column is what makes the lookup of a model
#: with a uuid primary key fail on a row of a model with an integer one. Why
#: each model below has its tables - granted on by the bootstrap, written by
#: the fixtures, or read by a lookup which must not take the cast - is told
#: by the module which declares them: ``accounts/models/guardian.py`` and
#: ``registry/models/guardian.py``. This list is that same set as data:
#: ``accounts.checks`` compares the two, so a declared role-managed model
#: really has its pair and the modules cannot drift from the list unnoticed.
#:
#: Being listed here says nothing about ownership: a model may need the
#: dedicated tables long before it is a role-managed resource. Every model of
#: ``ROLE_MANAGED_MODELS`` must nevertheless appear here as well.
GUARDIAN_PERF_MODELS = ['accounts.Organization',
                        'auth.Group',
                        'registry.WebMapService',
                        'registry.WebFeatureService',
                        'registry.CatalogueService',
                        'registry.MapContext',
                        'registry.MapContextLayer',
                        'registry.WebMapServiceMonitoringSetting']


DEFAULT_SETTINGS_FOR_REACT_CLIENT = {
    'react-client': {
        'tables': {
            'WebMapService': {
                'id': {
                    'show': False,
                    'order': 1,
                },
                'title': {
                    'show': True,
                    'order': 2,
                },
                'stringRepresentation': {
                    'show': False,
                    'order': 3
                }
            }

        }
    }
}
