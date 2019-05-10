from django.db import models


class Permission(models.Model):
    can_create_group = models.BooleanField(default=False)
    can_delete_group = models.BooleanField(default=False)
    can_edit_group = models.BooleanField(default=False)

    can_add_user_to_group = models.BooleanField(default=False)
    can_remove_user_from_group = models.BooleanField(default=False)

    can_change_group_role = models.BooleanField(default=False)

    can_activate_service = models.BooleanField(default=False)
    can_register_service = models.BooleanField(default=False)
    can_remove_service = models.BooleanField(default=False)
    # more permissions coming

    def __str__(self):
        return str(self.id)

    def get_permission_list(self):
        p_list = []
        perms = self.__dict__
        del perms["id"]
        del perms["_state"]
        for perm_key, perm_val in perms.items():
            if perm_val:
                p_list.append(perm_key)
        return p_list


class Role(models.Model):
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=200)
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, null=True)

    def __str__(self):
        return self.name


class Contact(models.Model):
    person_name = models.CharField(max_length=200, default="", null=True)
    email = models.CharField(max_length=100, null=True)
    phone = models.CharField(max_length=100, null=True)
    city = models.CharField(max_length=100, null=True)
    postal_code = models.CharField(max_length=100, null=True)
    street = models.CharField(max_length=100, null=True)
    address_type = models.CharField(max_length=100, null=True)
    address = models.CharField(max_length=100, null=True)
    state_or_province = models.CharField(max_length=100, null=True)
    country = models.CharField(max_length=100, null=True)

    def __str__(self):
        return self.person_name

    class Meta:
        abstract = True


class User(Contact):
    username = models.CharField(max_length=50)
    logged_in = models.BooleanField(default=False)
    salt = models.CharField(max_length=500)
    password = models.CharField(max_length=500)
    last_login = models.DateTimeField(null=True)
    created_on = models.DateTimeField(auto_now_add=True)
    groups = models.ManyToManyField('Group', related_name='users', null=True)
    primary_organization = models.ForeignKey('Organization', related_name='primary_users', on_delete=models.DO_NOTHING, null=True, blank=True)
    secondary_organization = models.ForeignKey('Organization', related_name='secondary_users', on_delete=models.DO_NOTHING, null=True, blank=True)

    def __str__(self):
        return self.username


class Organization(Contact):
    organization_name = models.CharField(max_length=255, null=True, default="")
    description = models.CharField(max_length=500, null=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, blank=True, null=True)

    def __str__(self):
        if self.organization_name is None:
            return ""
        return self.organization_name


class Group(models.Model):
    name = models.CharField(max_length=255)
    description = models.CharField(max_length=1000)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, blank=True, null=True, related_name="children")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, null=True)
    created_by = models.ForeignKey(User, on_delete=models.DO_NOTHING)

    def __str__(self):
        return self.name

