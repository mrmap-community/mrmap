# Permissions

MrMap v1.0.0 uses [django-guardian](https://github.com/django-guardian/django-guardian) as object-based permissions framework. Object-based permissions enable an administrator to grant users or groups the ability to perform an action on arbitrary subsets of objects in MrMap, rather than all objects of a certain type. For example, it is possible to grant a user permission to view only resources within by Organization membership.

# Roles
We group guardian permissions in MrMap by custom role system.

## Default Roles
By default, there are the following roles to group permissions.

* **Organization administrator** - Can grant role membership to users, accept or deny publishing rights and has editing rights for the organization.
* **Resource administrator** - Can add, edit and remove resources for his organization

## Models
ERM

### TemplateRole
A template role collects in MrMap a set of permissions. 

**Definition 1:** 
 
$P \widehat{=}  \textrm{ all permissions}$

### OwnerBasedTemplateRole
Collects a set of users to group them by a specific template role.

**Definition 2:**

$OwnR \widehat{=} \textrm{ user set of an OwnerBasedTemplateRole instance}$

### ObjectBasedTemplateRole
Grands a set of users a set of permissions which are inherited by the based template role.

**Definition 2:** 

$ObjR \widehat{=} \textrm{ user set of an ObjectBasedTemplateRole instance}$

### Correlation between the models

$\forall \textrm{ role } \in \textrm{ OwnerBasedTemplateRoles }, \exists \textrm{ ObjectBasedTemplateRole}$

$user \in ObjR, \in | \notin OwnR$

$user \in ObjR_{1}, \in OwnR$

# Publishing rights
An organization can grant publishing rights for other organizations.

