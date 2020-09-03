"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 16.07.20

"""
from time import time

from django.core.management import BaseCommand
from django.db import transaction

from service.helper.enums import MetadataEnum
from service.models import Metadata


class Command(BaseCommand):
    help = "(DEV COMMAND) Deletes all current metadata records from the database."

    def add_arguments(self, parser):
        pass

    @transaction.atomic
    def handle(self, *args, **options):
        mds = Metadata.objects.all()
        self.stdout.write(self.style.NOTICE("Found {} records. Start removing...".format(mds.count())))
        t_start = time()
        for md in mds:
            md.delete()
        self.stdout.write(self.style.NOTICE("Removing finished. Took {}s".format(time() - t_start)))
