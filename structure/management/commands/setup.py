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

from structure.models import User


class Command(BaseCommand):
    help = "Runs an initial setup for creating the superuser on a fresh installation."

    def add_arguments(self, parser):
        parser.add_argument("superuser-name", nargs="+", type=str, help="The superuser's username")

    def handle(self, *args, **options):
        # Check if superuser already exists
        name = options["superuser-name"]
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
            password = getpass("Enter a password: ")
            password_conf = getpass("Enter the password again: ")

        superuser.salt = str(os.urandom(25).hex())
        superuser.password = make_password(password, salt=superuser.salt)
        self.stdout.write(self.style.ERROR(superuser.password))
        superuser.name = "root"
        # ToDO: Finish this mess!

