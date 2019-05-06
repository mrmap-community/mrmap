from django.db import models


class Permissions(models.Model):
    can_create_group = models.BooleanField(default=False)
    can_edit_group = models.BooleanField(default=False)
    can_add_user_to_group = models.BooleanField(default=False)
    can_remove_user_from_group = models.BooleanField(default=False)
    can_activate_wms = models.BooleanField(default=False)
    can_remove_wms = models.BooleanField(default=False)
    can_register_wms = models.BooleanField(default=False)
    can_register_wfs = models.BooleanField(default=False)
    can_activate_wfs = models.BooleanField(default=False)
    can_remove_wfs = models.BooleanField(default=False)
    # more permissions coming


class Role(models.Model):
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=200)
    permissions = models.ManyToManyField(Permissions)

    def __str__(self):
        return self.name


class Contact(models.Model):
    name = models.CharField(max_length=100)
    email = models.CharField(max_length=100)
    phone = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=100)
    street = models.CharField(max_length=100)

    def __str__(self):
        return self.name

    class Meta:
        abstract = True


class User(Contact):
    username = models.CharField(max_length=50)
    salt = models.CharField(max_length=500)
    password = models.CharField(max_length=500)
    last_login = models.DateTimeField()
    created_on = models.DateTimeField(auto_now_add=True)
    groups = models.ManyToManyField('Group')


class Organization(Contact):
    description = models.CharField(max_length=200)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, blank=True, null=True)


class Group(models.Model):
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=100)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, blank=True, null=True)
    role = models.ForeignKey(Role, on_delete=models.DO_NOTHING, null=True)

    def __str__(self):
        return self.name


# class UserGroupRoleRel(models.Model):
#     user = models.ForeignKey(User, on_delete=models.CASCADE)
#     group = models.ForeignKey(Group, on_delete=models.CASCADE)
#     role = models.ForeignKey(Role, on_delete=models.CASCADE)

