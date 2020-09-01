"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 01.09.20

"""
from django.core.management import BaseCommand

from MrMap.cacher import DocumentCacher, SimpleCacher
from service.helper.enums import OGCOperationEnum, OGCServiceVersionEnum


class Command(BaseCommand):
    help = "(DEV COMMAND) Clears caches."

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        cacher = SimpleCacher(0)
        cached_keys = cacher.get_keys("*")
        self.stdout.write(
            self.style.NOTICE(
                "Found {} cached entries".format(len(cached_keys))
            )
        )
        for key in cached_keys:
            cacher.remove(key, False)
            self.stdout.write(self.style.INFO("    -- Removed {}".format(key)))

        self.stdout.write(self.style.SUCCESS("Cache cleared!"))
