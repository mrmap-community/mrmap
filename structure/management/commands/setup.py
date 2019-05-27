"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 06.05.19

"""
from getpass import getpass

import os

from django.contrib.auth.hashers import make_password
from django.core.management import BaseCommand
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from structure.models import User, Group, Role, Permission, Organization


class Command(BaseCommand):
    help = "Runs an initial setup for creating the superuser on a fresh installation."

    def add_arguments(self, parser):
        pass

    @transaction.atomic
    def handle(self, *args, **options):
        # Check if superuser already exists
        name = input("Enter a username:")
        superuser = User()
        superuser.username = name

        if User.objects.filter(username=name).exists():
            self.stdout.write(self.style.NOTICE("User with that name already exists!"))
            return
        # check password
        password = getpass("Enter a password: ")
        password_conf = getpass("Enter the password again: ")
        while password != password_conf:
            self.stdout.write(self.style.ERROR("Passwords didn't match! Try again!"))
            password = getpass("Enter the password: ")
            password_conf = getpass("Enter the password again: ")

        superuser.salt = str(os.urandom(25).hex())
        superuser.password = make_password(password, salt=superuser.salt)
        superuser.confirmed_dsgvo = True
        superuser.is_active = True
        superuser.name = "root"
        superuser.save()
        msg = "Superuser '" + name + "' was created successfully!"
        self.stdout.write(self.style.SUCCESS(str(msg)))

        # handle default role
        self._create_default_role()

        # handle root group
        group = self._create_default_group(superuser)
        group.created_by = superuser
        group.users.add(superuser)
        group.save()

        # handle root organization
        orga = self._create_default_organization()
        superuser.primary_organization = orga
        superuser.save()
        msg = "Superuser '" + name + "' added to group '" + group.name + "'!"
        self.stdout.write(self.style.SUCCESS(str(msg)))
        msg = "Superuser '" + name + "' added to organization '" + orga.organization_name + "'!"
        self.stdout.write(self.style.SUCCESS(msg))

    def _create_default_group(self, user: User):
        group = Group.objects.get_or_create(name="_root_", created_by=user)[0]
        if group.role is None:
            role = Role.objects.get_or_create(name="_root_")[0]
            if role.permission is None:
                perm = Permission()

                perm.can_create_group = True
                perm.can_delete_group = True
                perm.can_edit_group = True

                perm.can_remove_user_from_group = True
                perm.can_add_user_to_group = True

                perm.can_register_service = True
                perm.can_activate_service = True
                perm.can_remove_service = True

                perm.save()
                role.permission = perm
            role.save()
            group.role = role
            group.created_by = user
        return group

    def _create_default_role(self):
        role = Role.objects.get_or_create(name="_default_")[0]
        if role.permission is None:
            perm = Permission()
            perm.save()
            role.permission = perm
            role.description = _("The default role for all groups. Has no permissions.")
        role.save()

    def _create_default_organization(self):
        orga = Organization.objects.get_or_create(organization_name="Testorganization")[0]

        return orga

