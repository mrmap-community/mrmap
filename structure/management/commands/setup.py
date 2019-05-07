"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 06.05.19

"""
from getpass import getpass

import os

from django.contrib.auth.hashers import make_password, check_password
from django.core.management import BaseCommand

from structure.models import User, Group, Role, Permission


class Command(BaseCommand):
    help = "Runs an initial setup for creating the superuser on a fresh installation."

    def add_arguments(self, parser):
        parser.add_argument("superuser-name", nargs=1, type=str, help="The superuser's username")

    def handle(self, *args, **options):
        # Check if superuser already exists
        name = options.get("superuser-name", None)[0]
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
        # self.stdout.write(self.style.ERROR(superuser.password))
        superuser.name = "root"
        superuser.save()
        msg = "Superuser '" + name + "' was created successfully!"
        self.stdout.write(self.style.SUCCESS(str(msg)))

        # handle root group
        group = Group.objects.get_or_create(name="_root_")[0]
        if group.role is None:
            role = Role.objects.get_or_create(name="_root_")[0]
            if role.permission is None:
                perm = Permission()
                perm.can_activate_wfs = True
                perm.can_activate_wms = True
                perm.can_add_user_to_group = True
                perm.can_create_group = True
                perm.can_edit_group = True
                perm.can_register_wfs = True
                perm.can_register_wms = True
                perm.can_remove_user_from_group = True
                perm.can_remove_wfs = True
                perm.can_remove_wms = True
                perm.save()
                role.permission = perm
            role.save()
            group.role = role
        group.users.add(superuser)
        group.save()
        msg = "Superuser '" + name + "' added to group '" + group.name + "'!"
        self.stdout.write(self.style.SUCCESS(str(msg)))

