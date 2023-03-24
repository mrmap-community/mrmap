# Permissions

MrMap v1.0.0 uses [django-guardian](https://github.com/django-guardian/django-guardian) as object-based permissions framework. Object-based permissions enable an administrator to grant users or groups the ability to perform an action on arbitrary subsets of objects in MrMap, rather than all objects of a certain type. For example, it is possible to grant a user permission to view only resources within by Organization membership.

# Roles
We group guardian permissions in MrMap by custom role system.

## Default Roles
By default, there are the following roles to group permissions.

* **Organization administrator** - Can grant role membership to users, accept or deny publishing rights and has editing rights for the organization.
* **Resource administrator** - Can add, edit and remove resources for his organization

## Models
[ ![entity–relationship model of the guardian_roles app](../media/models/guardian_roles/erm.png) ](../media/models/guardian_roles/erm.png)
*Above: entity–relationship model of the guardian_roles app*

### TemplateRole
A template role collects in MrMap a set of permissions.


### OwnerBasedRole
Collects a set of users to group them by a specific template role.

### ObjectBasedRole
Grands a set of users a set of permissions which are inherited by the based template role.

### Signals
We use [django-signals](https://docs.djangoproject.com/en/3.1/topics/signals/) to handle changes on the described models above.

The following list of handlers are implemented:
todo:

### Correlation between the models

!!! abstract "Lemma 1"
    $\forall \textrm{ role } \in \textrm{ OwnerBasedRoles }, \exists \textrm{ ObjectBasedRole}$

![Subsets of users in correlation between object and owner based roles.](../media/models/guardian_roles/user_sets.svg)

*Above: Subsets of users in a correlation between object and owner based roles.*



$user \in ObjR, \in | \notin OwnR$

$user \in ObjR_{1}, \in OwnR$

# Publishing rights
An organization can grant publishing rights for other organizations.
