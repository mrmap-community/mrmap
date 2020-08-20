"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 20.08.20

"""
from django.core.management import BaseCommand, call_command

from MrMap.settings import MIGRATABLE_APPS


class Command(BaseCommand):
    help = "(DEV COMMAND) Performs makemigrations for all relevant apps, defined in MrMap/settings.py"

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        for app in MIGRATABLE_APPS:
            call_command(
                "makemigrations",
                app
            )

