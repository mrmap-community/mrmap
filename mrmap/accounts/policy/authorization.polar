# grant all rights to superadminusers
allow(_user: accounts::User{is_superuser: true}, _action: String, _resource);


has_permission(user: accounts::User, "view", wms: registry::WebMapService) if
    has_role(user, "member", wms);



# # Access role assignments stored in the application
# has_role(user: User, name: String, resource: Resource) if
#   role in user.roles and
#   role.name = name and
#   role.resource = resource;

# allow(user: accounts::User, "view", organization: accounts::Organization) if
#     organization in user.groups.all();

