# Permissions

MrMap v1.0.0 uses [django-guardian](https://github.com/django-guardian/django-guardian) as object-based permissions framework. Object-based permissions enable an administrator to grant users or groups the ability to perform an action on arbitrary subsets of objects in MrMap, rather than all objects of a certain type. For example, it is possible to grant a user permission to view only resources within by Organization membership.

# Roles
We group guardian permissions in MrMap by custom role system. 

## Default Roles
By default, there are the following roles to group permissions.

* **Organization administrator** - Can grant role membership to users, accept or deny publishing rights and has editing rights for the organization.
* **Resource administrator** - Can add, edit and remove resources for his organization

# Publishing rights
An organization can grant publishing rights for other organizations.