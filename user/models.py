from django.db import models

class Role(models.Model):
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=200)

class Contact(models.Model):
    name = models.CharField(max_length=100)
    email = models.CharField(max_length=100)
    phone = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=100)
    street = models.CharField(max_length=100)

    class Meta:
        abstract = True

class User(Contact):
    salt = models.CharField(max_length=100)
    password = models.CharField(max_length=250)
    last_login = models.DateTimeField()
    created_on = models.DateTimeField(auto_now_add=True)

class Organization(Contact):
    description = models.CharField(max_length=200)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, blank=True, null=True)

class Group(models.Model):
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=100)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, blank=True, null=True)

class UserGroupRoleRel(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    group = models.ForeignKey(Group, on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.CASCADE)

class Permissions(models.Model):
    can_create_group = models.BooleanField()
    can_edit_group = models.BooleanField()
    can_register_wms = models.BooleanField()
    # more permissions coming
    user = models.ForeignKey(User, on_delete=models.CASCADE)


