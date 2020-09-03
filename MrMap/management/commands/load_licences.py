"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 02.07.20

"""
from django.core.management import BaseCommand
from django.db import transaction

from MrMap.management.commands.setup_settings import LICENCES
from service.models import Licence


class Command(BaseCommand):
    help = "Loads licences, declared in the settings.py, into the database."

    def add_arguments(self, parser):
        pass

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Load licences..."))
        num_new_licences, num_updated_licences, num_deactivated_licences = self._create_default_licences()
        self.stdout.write(self.style.SUCCESS(
            str(
                "{} licences have been added.\n{} licences have been updated.\n{} licences have been deactivated.".format(num_new_licences, num_updated_licences, num_deactivated_licences)
            )
        ))

    @staticmethod
    def _create_default_licences() -> (int, int, int):
        """ Creates an initial amount of licences

        Returns:

        """
        # Create / Update licences
        num_new_licences = 0
        num_updated_licences = 0
        for licence in LICENCES:
            existing_licence = Licence.objects.get_or_create(
                identifier=licence.get("identifier", None)
            )
            num_new_licences += 1 if existing_licence[1] is True else 0
            num_updated_licences += 1 if existing_licence[1] is False else 0
            existing_licence = existing_licence[0]

            # Overwrite every other attribute with the settings.py data
            existing_licence.name = licence.get("name", None)
            existing_licence.identifier = licence.get("identifier", None)
            existing_licence.description = licence.get("description", None)
            existing_licence.description_url = licence.get("description_url", None)
            existing_licence.symbol_url = licence.get("symbol_url", None)
            existing_licence.is_open_data = licence.get("is_open_data", False)
            existing_licence.is_active = True

            existing_licence.save()

        # Deactivate licences, which are not present in LICENCES anymore
        num_deactivated_licences = 0
        active_licences = Licence.objects.filter(is_active=True)
        identifier_keys = [licence["identifier"] for licence in LICENCES]
        for licence in active_licences:
            if licence.identifier not in identifier_keys:
                licence.is_active = False
                licence.save()
                num_deactivated_licences += 1

        return num_new_licences, num_updated_licences, num_deactivated_licences