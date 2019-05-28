"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 28.05.19

"""

from django.db import models
from structure.models import Contact


class User(Contact):
    username = models.CharField(max_length=50)
    logged_in = models.BooleanField(default=False)
    salt = models.CharField(max_length=500)
    password = models.CharField(max_length=500)
    last_login = models.DateTimeField(null=True)
    created_on = models.DateTimeField(auto_now_add=True)
    groups = models.ManyToManyField('structure.Group', related_name='users', null=True)
    primary_organization = models.ForeignKey('structure.Organization', related_name='primary_users', on_delete=models.DO_NOTHING, null=True, blank=True)
    secondary_organization = models.ForeignKey('structure.Organization', related_name='secondary_users', on_delete=models.DO_NOTHING, null=True, blank=True)
    confirmed_newsletter = models.BooleanField(default=False)
    confirmed_survey = models.BooleanField(default=False)
    confirmed_dsgvo = models.DateTimeField(null=True, blank=True) # ToDo: For production this is not supposed to be nullable!!!
    is_active = models.BooleanField(default=False)

    def __str__(self):
        return self.username


class UserActivation(models.Model):
    user = models.ForeignKey(User, null=False, blank=False, on_delete=models.DO_NOTHING)
    activation_until = models.DateTimeField(null=True)
    activation_hash = models.CharField(max_length=500, null=False, blank=False)

    def __str__(self):
        return self.user.username