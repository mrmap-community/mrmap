"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 02.07.20

"""
from django.core.management import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Loads licences, declared in the settings.py, into the database."

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
    def _create_default_licences():
        """ Creates an initial amount of licences

        Returns:

        """
        # Create / Update licences
        num_new_licences = 0
        num_updated_licences = 0
        # Deactivate licences, which are not present in LICENCES anymore
        num_deactivated_licences = 0
        """
        active_licences = Licence.objects.all()
        identifier_keys = [licence["identifier"] for licence in LICENCES]
        for licence in active_licences:
            if licence.identifier not in identifier_keys:
                licence.is_active = False
                licence.save()
                num_deactivated_licences += 1
        """
        return num_new_licences, num_updated_licences, num_deactivated_licences
